#!/usr/bin/env python3
"""
图像伪造 / 篡改检测脚本（image-forgery-detector Skill）。

本脚本对 JPEG/PNG 等图片做多维度启发式分析，输出 JSON 格式的风险评分、
发现项（findings）与文字结论。算法思路源自 PictureMaterialDetect.java /
PictureTamperDetect.java 的 Python 移植版。

主要检测维度（详见下方各 section）：
- 元数据：EXIF、编辑软件关键词、AIGC 标识
- 视觉与局部特征：纹理、梯度、噪声、ELA 等
- 截图特征：常见屏幕比例、界面元素
- 文档篡改：证照类版式与局部不一致

命令行用法::

    python detect.py <image_path_or_url>

输出：stdout 打印 JSON，包含 overall_risk_score、conclusion、findings 等字段。

依赖：numpy、Pillow（PIL）。大图会自动缩放到 MAX_ANALYSIS_EDGE 以控制耗时。

面向小白：本文件较长（约 1700 行），按 section 分段阅读即可，无需逐行理解。
"""

import sys
import json
import math
import struct
import io
import os
import re
import traceback
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlparse

import numpy as np
from PIL import Image

# ── Constants（全局常量：图像类型、量化表、关键词列表等）────────────────────

TYPE_JPEG = "jpeg"
TYPE_PNG = "png"
MAX_ANALYSIS_EDGE = 1280
LOCAL_FEATURE_FULL_SCAN_PIXELS = 900_000

STANDARD_LUMA_QT = np.array([
    16, 11, 10, 16, 24, 40, 51, 61,
    12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56,
    14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77,
    24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101,
    72, 92, 95, 98, 112, 100, 103, 99
], dtype=np.int32)

COMMON_SCREEN_RATIOS = [
    16 / 9, 9 / 16, 19.5 / 9, 9 / 19.5, 20 / 9, 9 / 20,
    16 / 10, 10 / 16, 3 / 2, 2 / 3, 21 / 9, 9 / 21
]

EDIT_SOFTWARE_KEYWORDS = [
    "photoshop", "adobe", "lightroom", "camera raw", "gimp", "imagemagick",
    "canva", "pixlr", "photopea", "snapseed", "picsart", "vsco",
    "meitu", "美图秀秀", "美图修图", "facetune", "faceu", "b612",
    "dall-e", "midjourney", "stable diffusion", "stability ai", "runwayml",
    "doubao", "豆包", "元宝", "capcut", "剪映",
    "corel", "affinity", "krita", "topaz", "exiftool",
    "tensorflow", "pytorch", "gan", "aigc",
]

AIGC_METADATA_KEYWORDS = [
    "aigc", '"label":"1"', '"label": "1"',
    "contentproducer", "contentpropagator", "produceid", "propagateid",
    "tc260pg", "sm2", "sm3", "phash",
    "doubao", "豆包", "元宝",
]

# ── Data Classes（分析结果与像素访问的封装类）────────────────────────────────

class AnalysisResult:
    def __init__(self):
        self.image_path = ""
        self.image_type = ""
        self.file_size = 0
        self.width = 0
        self.height = 0
        self.metadata = {}
        self.visual = {}
        self.local = {}
        self.screenshot = {}
        self.document = {}
        self.overall_risk_score = 0
        self.tamper_index = 0
        self.forgery_score = 0
        self.tamper_evidence_count = 0
        self.suspicious = False
        self.suspected_edited = False
        self.suspected_screenshot = False
        self.review_status = ""
        self.conclusion = ""
        self.risk_labels = []
        self.findings = []

    def to_dict(self):
        def _convert(v):
            if isinstance(v, (np.integer,)):
                return int(v)
            if isinstance(v, (np.floating,)):
                return float(v)
            if isinstance(v, (np.bool_,)):
                return bool(v)
            if isinstance(v, dict):
                return {k: _convert(vv) for k, vv in v.items()}
            if isinstance(v, (list, tuple)):
                return [_convert(x) for x in v]
            return v
        return _convert({
            "image_path": self.image_path,
            "image_type": self.image_type,
            "file_size": self.file_size,
            "width": self.width,
            "height": self.height,
            "metadata_inspection": self.metadata,
            "visual_inspection": self.visual,
            "local_feature_inspection": self.local,
            "screenshot_inspection": self.screenshot,
            "document_tamper_inspection": self.document,
            "overall_risk_score": self.overall_risk_score,
            "tamper_index": self.tamper_index,
            "forgery_score": self.forgery_score,
            "tamper_evidence_count": self.tamper_evidence_count,
            "suspicious": self.suspicious,
            "suspected_edited": self.suspected_edited,
            "suspected_screenshot": self.suspected_screenshot,
            "review_status": self.review_status,
            "conclusion": self.conclusion,
            "risk_labels": self.risk_labels,
            "findings": self.findings,
        })


class AnalysisPixels:
    def __init__(self, img_array, gray_array):
        self.rgb = img_array
        self.gray = gray_array
        self.height, self.width = gray_array.shape

    def gray_at(self, x, y):
        return int(self.gray[y, x])

    def is_page_paper(self, x, y):
        r, g, b = self.rgb[y, x]
        mx = max(r, g, b)
        mn = min(r, g, b)
        brightness = mx / 255.0
        saturation = 0.0 if mx == 0 else (mx - mn) / mx
        return brightness >= 0.58 and saturation <= 0.28


# ── Image Loading（从本地路径或 URL 加载图片并转为 numpy 数组）──────────────

def read_image_from_path(path_or_url):
    if re.match(r'^https?://', path_or_url):
        req = Request(path_or_url, headers={'User-Agent': 'Mozilla/5.0'})
        data = urlopen(req, timeout=30).read()
        img = Image.open(io.BytesIO(data))
        image_bytes = data
    else:
        path = Path(path_or_url)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path_or_url}")
        image_bytes = path.read_bytes()
        img = Image.open(io.BytesIO(image_bytes))

    return img, image_bytes


def detect_image_type(image_bytes, file_name=""):
    if len(image_bytes) >= 3 and image_bytes[0] == 0xff and image_bytes[1] == 0xd8 and image_bytes[2] == 0xff:
        return TYPE_JPEG
    if len(image_bytes) >= 8 and image_bytes[0] == 0x89 and image_bytes[1] == 0x50 and image_bytes[2] == 0x4e and image_bytes[3] == 0x47:
        return TYPE_PNG
    lower = file_name.lower()
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return TYPE_JPEG
    if lower.endswith(".png"):
        return TYPE_PNG
    return "unknown"


def build_analysis_pixels(pil_image):
    w, h = pil_image.size
    if max(w, h) > MAX_ANALYSIS_EDGE:
        scale = MAX_ANALYSIS_EDGE / max(w, h)
        nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
        pil_image = pil_image.resize((nw, nh), Image.Resampling.BILINEAR)

    if pil_image.mode != "RGB":
        pil_image = pil_image.convert("RGB")

    w, h = pil_image.size
    rgb_array = np.array(pil_image, dtype=np.int32)
    gray_array = np.round(
        0.299 * rgb_array[:, :, 0] + 0.587 * rgb_array[:, :, 1] + 0.114 * rgb_array[:, :, 2]
    ).astype(np.int32)

    return AnalysisPixels(rgb_array, gray_array), (rgb_array.shape[1], rgb_array.shape[0])


# ── Utility Functions（通用数学/图像小工具函数）──────────────────────────────

def clamp_score(score):
    return max(0, min(100, score))


def rd(value):
    return round(value, 3)


def scale_linear(value, low, high, out_min, out_max):
    if value <= low:
        return out_min
    if value >= high:
        return out_max
    return out_min + (value - low) / (high - low) * (out_max - out_min)


def median(lst):
    if not lst:
        return 0.0
    s = sorted(lst)
    n = len(s)
    if n % 2 == 0:
        return (s[n // 2 - 1] + s[n // 2]) / 2.0
    return float(s[n // 2])


# ── JPEG Parsing（解析 JPEG 二进制：段标记、量化表、APP 元数据等）──────────

def read_u16(data, offset, little_endian=False):
    if offset + 2 > len(data):
        return 0
    if little_endian:
        return data[offset] | (data[offset + 1] << 8)
    return (data[offset] << 8) | data[offset + 1]


def read_u32(data, offset, little_endian=False):
    if offset + 4 > len(data):
        return 0
    if little_endian:
        return data[offset] | (data[offset + 1] << 8) | (data[offset + 2] << 16) | (data[offset + 3] << 24)
    return (data[offset] << 24) | (data[offset + 1] << 16) | (data[offset + 2] << 8) | data[offset + 3]


def parse_jpeg_segments(data):
    info = {"jfif": False, "adobe": False, "exif_payload": None, "quantization_tables": []}

    if len(data) < 4 or data[0] != 0xff or data[1] != 0xd8:
        return info

    idx = 2
    while idx + 3 < len(data):
        if data[idx] != 0xff:
            idx += 1
            continue
        while idx < len(data) and data[idx] == 0xff:
            idx += 1
        if idx >= len(data):
            break

        marker = data[idx]
        idx += 1
        if marker == 0xd9 or marker == 0xda:
            break
        if idx + 1 >= len(data):
            break

        length = read_u16(data, idx)
        if length < 2 or idx + length > len(data):
            break
        payload_start = idx + 2
        payload_length = length - 2

        if marker == 0xe0 and payload_length >= 5:
            ident = data[payload_start:payload_start + 5].decode("ascii", errors="replace")
            info["jfif"] = (ident == "JFIF\x00")
        elif marker == 0xee and payload_length >= 5:
            ident = data[payload_start:payload_start + 5].decode("ascii", errors="replace")
            info["adobe"] = (ident == "Adobe")
        elif marker == 0xe1 and payload_length >= 6:
            if data[payload_start:payload_start + 6] == b"Exif\x00\x00":
                info["exif_payload"] = data[payload_start + 6:payload_start + payload_length]
        elif marker == 0xdb:
            _parse_dqt(data, payload_start, payload_length, info["quantization_tables"])

        idx += length

    return info


def _parse_dqt(data, start, length, tables):
    idx = start
    end = start + length
    while idx < end:
        table_info = data[idx]
        idx += 1
        precision = (table_info >> 4) & 0x0f
        values_per_table = 64 if precision == 0 else 128
        if idx + values_per_table > end:
            break
        table = []
        if precision == 0:
            for i in range(64):
                table.append(data[idx + i])
        else:
            for i in range(64):
                table.append(read_u16(data, idx + i * 2))
        tables.append(table)
        idx += values_per_table


def parse_exif(payload):
    exif = {"exif_present": False, "make": None, "model": None, "software": None,
            "date_time": None, "date_time_original": None, "gps_present": False, "user_comment": None}

    if payload is None or len(payload) < 8:
        return exif

    if payload[0] == 0x49 and payload[1] == 0x49:
        le = True
    elif payload[0] == 0x4d and payload[1] == 0x4d:
        le = False
    else:
        return exif

    exif["exif_present"] = True
    first_ifd = read_u32(payload, 4, le)
    if first_ifd <= 0 or first_ifd >= len(payload):
        return exif

    _parse_ifd(payload, first_ifd, le, exif, True)
    return exif


def _parse_ifd(data, offset, le, exif, allow_sub):
    if offset + 2 > len(data):
        return
    entry_count = read_u16(data, offset, le)
    entry_base = offset + 2
    for i in range(entry_count):
        entry_off = entry_base + i * 12
        if entry_off + 12 > len(data):
            break
        tag = read_u16(data, entry_off, le)
        typ = read_u16(data, entry_off + 2, le)
        cnt = read_u32(data, entry_off + 4, le)
        value_or_offset = read_u32(data, entry_off + 8, le)

        if tag == 0x010f:
            exif["make"] = _read_exif_string(data, typ, cnt, value_or_offset, le, entry_off + 8)
        elif tag == 0x0110:
            exif["model"] = _read_exif_string(data, typ, cnt, value_or_offset, le, entry_off + 8)
        elif tag == 0x0131:
            exif["software"] = _read_exif_string(data, typ, cnt, value_or_offset, le, entry_off + 8)
        elif tag == 0x0132:
            exif["date_time"] = _read_exif_string(data, typ, cnt, value_or_offset, le, entry_off + 8)
        elif tag == 0x9003:
            exif["date_time_original"] = _read_exif_string(data, typ, cnt, value_or_offset, le, entry_off + 8)
        elif tag == 0x9286:
            exif["user_comment"] = _read_tag_text(data, typ, cnt, value_or_offset, le, entry_off + 8)
        elif tag == 0x8825:
            exif["gps_present"] = (value_or_offset > 0)
        elif allow_sub and tag == 0x8769 and value_or_offset > 0:
            _parse_ifd(data, value_or_offset, le, exif, False)


def _read_exif_string(data, typ, cnt, value_or_offset, le, inline_off):
    if typ != 2 or cnt <= 0:
        return None
    if cnt <= 4:
        end = min(len(data), inline_off + cnt)
        return data[inline_off:end].decode("ascii", errors="replace")
    if value_or_offset < 0 or value_or_offset + cnt > len(data):
        return None
    return data[value_or_offset:value_or_offset + cnt].decode("ascii", errors="replace").replace("\x00", "").strip()


def _read_tag_text(data, typ, cnt, value_or_offset, le, inline_off):
    if typ == 2:
        return _read_exif_string(data, typ, cnt, value_or_offset, le, inline_off)
    if typ != 7 or cnt <= 0:
        return None

    if cnt <= 4:
        data_start, data_len = inline_off, cnt
    else:
        if value_or_offset < 0 or value_or_offset + cnt > len(data):
            return None
        data_start, data_len = value_or_offset, cnt

    if data_start + data_len > len(data):
        return None

    payload_start, payload_len = data_start, data_len
    if payload_len > 8:
        header = data[data_start:data_start + 8].decode("ascii", errors="replace").upper()
        if header.startswith("ASCII") or header.startswith("UNICODE") or header.startswith("JIS"):
            payload_start += 8
            payload_len -= 8

    return data[payload_start:payload_start + payload_len].decode("utf-8", errors="replace").replace("\x00", "").strip()


def parse_png_exif_payload(data):
    if data is None or len(data) < 8:
        return None
    idx = 8
    while idx + 12 <= len(data):
        length = read_u32(data, idx)
        typ = data[idx + 4:idx + 8].decode("ascii", errors="replace")
        if idx + 12 + length > len(data):
            break
        if typ == "eXIf":
            return data[idx + 8:idx + 8 + length]
        idx += length + 12
    return None


def parse_png_text_chunks(data):
    result = {}
    if len(data) < 8:
        return result
    idx = 8
    while idx + 8 <= len(data):
        length = read_u32(data, idx)
        if idx + 12 + length > len(data):
            break
        typ = data[idx + 4:idx + 8].decode("ascii", errors="replace")
        chunk_data = data[idx + 8:idx + 8 + length]
        if typ == "tEXt":
            text = chunk_data.decode("iso-8859-1", errors="replace")
            null_pos = text.find("\x00")
            if null_pos > 0:
                result[text[:null_pos]] = text[null_pos + 1:]
        elif typ == "iTXt":
            text = chunk_data.decode("utf-8", errors="replace")
            null_pos = text.find("\x00")
            if null_pos > 0:
                result[text[:null_pos]] = text[null_pos + 1:].replace("\x00", "")
        idx += length + 12
    return result


# ── JPEG Analysis（基于 JPEG 结构的篡改线索分析）────────────────────────────

def estimate_jpeg_quality(quantization_tables):
    if not quantization_tables:
        return -1
    qt = np.array(quantization_tables[0], dtype=np.int32)
    if len(qt) != 64:
        return -1

    best_q, best_diff = 1, 10**18
    for quality in range(1, 101):
        scale = 5000 // quality if quality < 50 else 200 - quality * 2
        expected = ((STANDARD_LUMA_QT.astype(np.int64) * scale + 50) // 100)
        expected = np.clip(expected, 1, 255)
        diff = int(np.sum(np.abs(expected.astype(np.int64) - qt.astype(np.int64))))
        if diff < best_diff:
            best_diff = diff
            best_q = quality
    return best_q


def calculate_blockiness(pixels):
    h, w = pixels.gray.shape
    gray = pixels.gray.astype(np.float64)

    diff_h = np.abs(np.diff(gray, axis=1))
    boundary_h = diff_h[:, 7::8].sum() if w > 8 else 0
    inner_h = np.delete(diff_h, np.s_[7::8], axis=1).sum()
    boundary_h_count = diff_h[:, 7::8].size if w > 8 else 0
    inner_h_count = diff_h.size - boundary_h_count

    diff_v = np.abs(np.diff(gray, axis=0))
    boundary_v = diff_v[7::8, :].sum() if h > 8 else 0
    inner_v = np.delete(diff_v, np.s_[7::8], axis=0).sum()
    boundary_v_count = diff_v[7::8, :].size if h > 8 else 0
    inner_v_count = diff_v.size - boundary_v_count

    boundary_avg = (boundary_h + boundary_v) / max(1, boundary_h_count + boundary_v_count)
    inner_avg = (inner_h + inner_v) / max(1, inner_h_count + inner_v_count)

    return 0.0 if inner_avg == 0 else boundary_avg / inner_avg


# ── Visual Features（全图视觉统计特征：亮度、对比度、色彩分布等）────────────

def inspect_visual(pixels):
    h, w = pixels.gray.shape
    step_x = max(1, w // 300)
    step_y = max(1, h // 300)

    samples = pixels.rgb[::step_y, ::step_x]
    grays = pixels.gray[::step_y, ::step_x].astype(np.float64)

    r = samples[:, :, 0].astype(np.float64)
    g = samples[:, :, 1].astype(np.float64)
    b = samples[:, :, 2].astype(np.float64)

    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    with np.errstate(divide='ignore', invalid='ignore'):
        sat = np.where(mx == 0, 0.0, (mx - mn) / mx)

    brightness = grays.ravel()
    brightness_sum = np.sum(brightness)
    brightness_sq_sum = np.sum(brightness ** 2)
    count = brightness.size
    mean_brightness = brightness_sum / count
    brightness_std = math.sqrt(max(0, brightness_sq_sum / count - mean_brightness ** 2))

    mean_saturation = float(np.mean(sat))

    bins = (r.astype(np.int32) >> 4) << 8 | (g.astype(np.int32) >> 4) << 4 | (b.astype(np.int32) >> 4)
    unique = len(np.unique(bins))
    palette_density = unique / count

    hist, _ = np.histogram(brightness, bins=256, range=(0, 255))
    hist = hist.astype(np.float64)
    hist_total = np.sum(hist)
    peaks = 0
    if hist_total > 0:
        for i in range(1, 255):
            if hist[i] > hist[i - 1] and hist[i] > hist[i + 1] and hist[i] > hist_total * 0.01:
                peaks += 1
    hist_peak_ratio = peaks / 255.0

    score = 0
    findings = []
    if brightness_std < 18 and palette_density < 0.025:
        score += 18
        findings.append("图片纹理变化较低，且颜色分布较单一。")
    if mean_saturation > 0.72 and brightness_std > 70:
        score += 10
        findings.append("图片饱和度和对比度疑似被明显增强。")
    if mean_brightness < 35 or mean_brightness > 220:
        score += 6
        findings.append("图片整体亮度异常偏高或偏低。")
    if hist_peak_ratio > 0.18:
        score += 8
        findings.append("亮度直方图存在较明显的峰值集中现象。")

    return {
        "mean_brightness": rd(mean_brightness),
        "brightness_std": rd(brightness_std),
        "mean_saturation": rd(mean_saturation),
        "palette_density": rd(palette_density),
        "histogram_peak_ratio": rd(hist_peak_ratio),
        "risk_score": clamp_score(score),
        "findings": findings,
    }


# ── Local Features（局部块级特征：检测区域间不一致）──────────────────────────

def sobel_x(pixels, x, y):
    g = pixels.gray
    return (-g[y - 1, x - 1] + g[y - 1, x + 1]
            - 2 * g[y, x - 1] + 2 * g[y, x + 1]
            - g[y + 1, x - 1] + g[y + 1, x + 1])


def sobel_y(pixels, x, y):
    g = pixels.gray
    return (g[y - 1, x - 1] + 2 * g[y - 1, x] + g[y - 1, x + 1]
            - g[y + 1, x - 1] - 2 * g[y + 1, x] - g[y + 1, x + 1])


def inspect_local(pixels):
    h, w = pixels.gray.shape
    grid_cols, grid_rows = 4, 4
    grid = np.zeros((grid_rows, grid_cols), dtype=np.int32)
    feature_count = 0
    step = 2 if w * h > LOCAL_FEATURE_FULL_SCAN_PIXELS else 1

    g = pixels.gray.astype(np.int32)
    gx = -g[1:-1, :-2] + g[1:-1, 2:] - 2 * g[:-2, 1:-1] + 2 * g[2:, 1:-1] - g[:-2, :-2] + g[:-2, 2:]
    gy = g[:-2, :-2] + 2 * g[:-2, 1:-1] + g[:-2, 2:] - g[2:, :-2] - 2 * g[2:, 1:-1] - g[2:, 2:]

    corner_like = np.minimum(np.abs(gx), np.abs(gy))
    mask = corner_like >= 28

    ys, xs = np.where(mask)
    if len(ys) > 0:
        feature_count = len(ys)
        cell_x = np.minimum(grid_cols - 1, xs * grid_cols // w)
        cell_y = np.minimum(grid_rows - 1, ys * grid_rows // h)
        np.add.at(grid, (cell_y, cell_x), 1)

    density = feature_count / max(1, w * h)
    max_cell = int(np.max(grid))
    active_cells = int(np.count_nonzero(grid > 0))
    concentration = 0.0 if feature_count == 0 else max_cell / feature_count

    score = 0
    findings = []
    if density < 0.01:
        score += 10
        findings.append("局部特征点密度较低。")
    if concentration > 0.24:
        score += 16
        findings.append("局部特征点在小范围内高度集中。")
    if active_cells <= 5 and feature_count > 0:
        score += 10
        findings.append("图像局部特征分布不均匀。")

    return {
        "feature_count": feature_count,
        "feature_density": rd(density),
        "max_grid_concentration": rd(concentration),
        "active_grid_cells": active_cells,
        "risk_score": clamp_score(score),
        "findings": findings,
    }


# ── Screenshot Features（截图判定：宽高比、边缘、状态栏等启发式）────────────

def calculate_edge_density(pixels):
    h, w = pixels.gray.shape
    if h < 3 or w < 3:
        return 0.0

    g = pixels.gray.astype(np.float64)
    gx = (-g[1:-1, :-2] + g[1:-1, 2:] - 2 * g[:-2, 1:-1] + 2 * g[2:, 1:-1] - g[:-2, :-2] + g[:-2, 2:])
    gy = (g[:-2, :-2] + 2 * g[:-2, 1:-1] + g[:-2, 2:] - g[2:, :-2] - 2 * g[2:, 1:-1] - g[2:, 2:])
    magnitude = np.abs(gx) + np.abs(gy)
    edges = np.sum(magnitude >= 90)
    total = magnitude.size
    return edges / max(1, total)


def estimate_text_row_ratio(pixels):
    h, w = pixels.gray.shape
    if h < 3:
        return 0.0

    g = pixels.gray.astype(np.float64)
    gx = -g[1:-1, :-2] + g[1:-1, 2:] - 2 * g[:-2, 1:-1] + 2 * g[2:, 1:-1] - g[:-2, :-2] + g[:-2, 2:]

    text_rows = 0
    for y_idx in range(h - 2):
        row = np.abs(gx[y_idx, :])
        row_edges = np.sum(row >= 70)
        ratio = row_edges / max(1, w)
        if 0.06 <= ratio <= 0.4:
            text_rows += 1

    return text_rows / max(1, h)


def estimate_flat_region_ratio(pixels):
    h, w = pixels.gray.shape
    block_size = max(8, min(w, h) // 40)
    flat, total = 0, 0

    for y in range(0, h, block_size):
        for x in range(0, w, block_size):
            total += 1
            block = pixels.gray[y:min(h, y + block_size), x:min(w, x + block_size)]
            if np.var(block.astype(np.float64)) < 30:
                flat += 1

    return flat / max(1, total)


def nearest_ratio_delta(ratio):
    return min(abs(ratio - cr) for cr in COMMON_SCREEN_RATIOS)


def inspect_screenshot(pixels, visual):
    w, h = pixels.gray.shape
    ratio = w / h
    nearest_delta = nearest_ratio_delta(ratio)
    edge_density = calculate_edge_density(pixels)
    text_row_ratio = estimate_text_row_ratio(pixels)
    flat_region_ratio = estimate_flat_region_ratio(pixels)

    score = 0
    findings = []
    if nearest_delta <= 0.03:
        score += 18
        findings.append("宽高比接近常见屏幕分辨率比例。")
    if flat_region_ratio >= 0.42:
        score += 16
        findings.append("大面积纯色区域疑似应用界面区域。")
    if text_row_ratio >= 0.08:
        score += 18
        findings.append("多行区域呈现出密集文本或菜单栏特征。")
    if edge_density >= 0.12:
        score += 10
        findings.append("边缘密度较高，符合截图类内容特征。")
    if visual.get("palette_density", 1) < 0.08 and flat_region_ratio > 0.35:
        score += 8
        findings.append("颜色密度和纯色区域组合特征指向截图或屏幕内容。")

    return {
        "aspect_ratio": rd(ratio),
        "nearest_screen_ratio_delta": rd(nearest_delta),
        "edge_density": rd(edge_density),
        "text_row_ratio": rd(text_row_ratio),
        "flat_region_ratio": rd(flat_region_ratio),
        "risk_score": clamp_score(score),
        "suspected_screenshot": score >= 40,
        "findings": findings,
    }


# ── Document Tamper Detection（证件/文档类图片篡改检测入口）──────────────────

def build_block_metric(pixels, page_mask, start_x, start_y, block_size):
    h, w = pixels.gray.shape
    ry, rx = page_mask.shape
    e_y = min(h, start_y + block_size)
    e_x = min(w, start_x + block_size)
    region = page_mask[start_y:e_y, start_x:e_x]
    gray_region = pixels.gray[start_y:e_y, start_x:e_x].astype(np.float64)

    page_mask_local = region
    total = page_mask_local.size
    page_count = int(np.sum(page_mask_local))
    if page_count == 0:
        return {"coverage": 0.0, "mean": 0.0, "std": 0.0, "dark_ratio": 0.0, "x": start_x, "y": start_y}

    values = gray_region[page_mask_local]
    mean = float(np.mean(values))
    std = float(np.std(values))
    dark = int(np.sum(values <= 150))
    dark_ratio = dark / page_count

    return {"coverage": page_count / total, "mean": mean, "std": std, "dark_ratio": dark_ratio, "x": start_x, "y": start_y}


def average_std(blocks):
    return np.mean([b["std"] for b in blocks]) if blocks else 0.0


def variance_of_std(blocks, mean_std):
    if not blocks:
        return 0.0
    return np.mean([(b["std"] - mean_std) ** 2 for b in blocks])


def calculate_block_anomaly_ratio(blocks, mean_std):
    suspicious = []
    effective = 0
    for block in blocks:
        if block["dark_ratio"] > 0.25:
            continue
        effective += 1
        if (block["std"] >= mean_std + 14 or block["std"] <= max(4, mean_std - 10)) and block["mean"] >= 150:
            suspicious.append(block)
    return suspicious, effective, len(suspicious) / max(1, effective)


def calculate_cluster_metrics(suspicious_blocks, block_size, page_pixels):
    if not suspicious_blocks or page_pixels == 0:
        return {"cluster_ratio": 0.0, "largest_cluster_coverage": 0.0}

    block_map = {}
    max_gx, max_gy = 0, 0
    for b in suspicious_blocks:
        gx = b["x"] // max(1, block_size)
        gy = b["y"] // max(1, block_size)
        block_map[f"{gx}:{gy}"] = b
        max_gx = max(max_gx, gx)
        max_gy = max(max_gy, gy)

    visited = np.zeros((max_gy + 2, max_gx + 2), dtype=bool)
    largest = 0
    for b in suspicious_blocks:
        sx = b["x"] // max(1, block_size)
        sy = b["y"] // max(1, block_size)
        if visited[sy, sx]:
            continue
        size = _flood_fill(block_map, visited, sx, sy)
        largest = max(largest, size)

    cluster_ratio = largest / max(1, len(suspicious_blocks))
    largest_cluster_coverage = (largest * block_size * block_size) / max(1, page_pixels)
    return {"cluster_ratio": rd(cluster_ratio), "largest_cluster_coverage": rd(largest_cluster_coverage)}


def _flood_fill(block_map, visited, start_x, start_y):
    count = 0
    stack = [(start_x, start_y)]
    visited[start_y, start_x] = True
    while stack:
        x, y = stack.pop()
        count += 1
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            nx, ny = x + dx, y + dy
            if 0 <= ny < visited.shape[0] and 0 <= nx < visited.shape[1]:
                if not visited[ny, nx] and f"{nx}:{ny}" in block_map:
                    visited[ny, nx] = True
                    stack.append((nx, ny))
    return count


def estimate_text_band_variance(pixels, page_mask, min_x, min_y, max_x, max_y):
    active_rows = []
    for y in range(min_y, max_y + 1):
        row_mask = page_mask[y, min_x:max_x + 1]
        page_count = int(np.sum(row_mask))
        if page_count == 0:
            continue
        dark = int(np.sum(pixels.gray[y, min_x:max_x + 1][row_mask] <= 165))
        dark_ratio = dark / page_count
        if 0.01 <= dark_ratio <= 0.35:
            active_rows.append(dark_ratio)

    if not active_rows:
        return 0.0
    mean = np.mean(active_rows)
    return float(np.mean([(v - mean) ** 2 for v in active_rows]))


def count_page_components(page_mask, min_x, min_y, max_x, max_y):
    visited = np.zeros_like(page_mask, dtype=bool)
    count = 0
    for y in range(max(0, min_y), min(page_mask.shape[0] - 1, max_y) + 1):
        for x in range(max(0, min_x), min(page_mask.shape[1] - 1, max_x) + 1):
            if page_mask[y, x] and not visited[y, x]:
                count += 1
                _flood_fill_page(page_mask, visited, x, y, min_x, min_y, max_x, max_y)
    return count


def _flood_fill_page(mask, visited, sx, sy, min_x, min_y, max_x, max_y):
    h, w = mask.shape
    stack = [(sx, sy)]
    visited[sy, sx] = True
    while stack:
        x, y = stack.pop()
        for nx, ny in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]:
            if min_x <= nx <= max_x and min_y <= ny <= max_y and 0 <= nx < w and 0 <= ny < h:
                if mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    stack.append((nx, ny))


# ── LBP Texture Inconsistency（LBP 纹理不一致：复制粘贴常见信号）──────────────

def build_lbp_histogram(pixels, page_mask, start_x, start_y, block_size):
    h, w = pixels.gray.shape
    hist = np.zeros(16, dtype=np.int32)
    step = max(1, block_size // 10)

    offsets = [(-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0)]

    for y in range(max(1, start_y), min(h - 1, start_y + block_size), step):
        for x in range(max(1, start_x), min(w - 1, start_x + block_size), step):
            if not page_mask[y, x]:
                continue
            center = pixels.gray[y, x]
            code = 0
            for i, (dx, dy) in enumerate(offsets):
                if pixels.gray[y + dy, x + dx] >= center:
                    code |= (1 << i)
            hist[(code >> 4) & 0x0f] += 1

    return hist


def histogram_distance(h1, h2):
    t1, t2 = int(np.sum(h1)), int(np.sum(h2))
    if t1 == 0 or t2 == 0:
        return 0.0
    return float(np.sum(np.abs(h1.astype(np.float64) / t1 - h2.astype(np.float64) / t2)) / 2.0)


def calculate_lbp_inconsistency(pixels, page_mask, blocks, block_size):
    if len(blocks) < 4:
        return 0.0

    histograms = {}
    block_map = {}
    for b in blocks:
        gx = b["x"] // max(1, block_size)
        gy = b["y"] // max(1, block_size)
        key = f"{gx}:{gy}"
        histograms[key] = build_lbp_histogram(pixels, page_mask, b["x"], b["y"], block_size)
        block_map[key] = b

    suspicious = 0
    effective = 0
    dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]

    for key, h in histograms.items():
        b = block_map[key]
        if b["dark_ratio"] > 0.25:
            continue
        effective += 1
        parts = key.split(":")
        gx, gy = int(parts[0]), int(parts[1])
        min_dist = float("inf")
        for dx, dy in dirs:
            nk = f"{gx + dx}:{gy + dy}"
            if nk in histograms:
                min_dist = min(min_dist, histogram_distance(h, histograms[nk]))
        if min_dist < float("inf") and min_dist >= 0.42:
            suspicious += 1

    return suspicious / max(1, effective)


# ── Gradient Incoherence（梯度不连贯：拼接边缘检测）────────────────────────────

def block_orientation_variance(pixels, page_mask, start_x, start_y, block_size):
    h, w = pixels.gray.shape
    angles = []
    step = max(1, block_size // 8)

    for y in range(max(1, start_y), min(h - 1, start_y + block_size), step):
        for x in range(max(1, start_x), min(w - 1, start_x + block_size), step):
            if not page_mask[y, x]:
                continue
            gx_val = sobel_x(pixels, x, y)
            gy_val = sobel_y(pixels, x, y)
            if abs(gx_val) + abs(gy_val) < 20:
                continue
            angles.append(math.atan2(gy_val, gx_val))

    if len(angles) < 6:
        return 0.0
    return float(np.var(angles))


def calculate_gradient_incoherence(pixels, page_mask, blocks, block_size):
    if len(blocks) < 4:
        return 0.0

    ori_var = {}
    block_map = {}
    for b in blocks:
        gx_key = b["x"] // max(1, block_size)
        gy_key = b["y"] // max(1, block_size)
        key = f"{gx_key}:{gy_key}"
        ori_var[key] = block_orientation_variance(pixels, page_mask, b["x"], b["y"], block_size)
        block_map[key] = b

    values = list(ori_var.values())
    med = median(values)
    if med <= 0.01:
        return 0.0

    suspicious = 0
    effective = 0
    for key, v in ori_var.items():
        b = block_map[key]
        if b["dark_ratio"] > 0.25:
            continue
        effective += 1
        ratio = v / med
        if ratio >= 2.0 or ratio <= 0.45:
            suspicious += 1

    return suspicious / max(1, effective)


# ── Noise Inconsistency（噪声分布不一致：不同来源区域拼接）────────────────────

def block_laplacian_variance(pixels, page_mask, start_x, start_y, block_size):
    h, w = pixels.gray.shape
    values = []
    page_count = 0

    for y in range(max(1, start_y), min(h - 1, start_y + block_size)):
        for x in range(max(1, start_x), min(w - 1, start_x + block_size)):
            if not page_mask[y, x]:
                continue
            page_count += 1
            center = pixels.gray[y, x]
            lap = (-pixels.gray[y - 1, x] - pixels.gray[y + 1, x]
                   - pixels.gray[y, x - 1] - pixels.gray[y, x + 1] + 4 * center)
            values.append(abs(lap))

    if page_count < block_size:
        return -1.0
    return float(np.var(values))


def calculate_noise_inconsistency(pixels, page_mask, min_x, min_y, max_x, max_y, block_size):
    if page_mask is None:
        return 0.0

    block_noise = []
    for y in range(min_y, max_y + 1, block_size):
        for x in range(min_x, max_x + 1, block_size):
            noise = block_laplacian_variance(pixels, page_mask, x, y, block_size)
            if noise >= 0:
                block_noise.append(noise)

    if len(block_noise) < 4:
        return 0.0
    med = median(block_noise)
    if med <= 1:
        return 0.0

    suspicious = sum(1 for n in block_noise if n / med >= 2.2 or n / med <= 0.42)
    return suspicious / len(block_noise)


# ── ELA (Error Level Analysis)（误差级分析：JPEG 重压缩痕迹）──────────────────

def reencode_jpeg(pil_image, quality=90):
    buf = io.BytesIO()
    try:
        pil_image.save(buf, format="JPEG", quality=quality)
        buf.seek(0)
        return Image.open(buf)
    except Exception:
        return None


def block_ela_mean(pixels_orig, pixels_ela, page_mask, start_x, start_y, block_size):
    h, w = pixels_orig.gray.shape
    e_y = min(h, start_y + block_size)
    e_x = min(w, start_x + block_size)

    region_mask = page_mask[start_y:e_y, start_x:e_x]
    diff = np.abs(pixels_orig.gray[start_y:e_y, start_x:e_x].astype(np.float64)
                  - pixels_ela.gray[start_y:e_y, start_x:e_x].astype(np.float64))
    diff_masked = diff[region_mask]
    count = diff_masked.size
    if count < block_size // 2:
        return -1.0
    return float(np.mean(diff_masked))


def calculate_ela_anomaly(pil_image, pixels, page_mask, min_x, min_y, max_x, max_y, block_size):
    recompressed = reencode_jpeg(pil_image, 90)
    if recompressed is None:
        return 0.0

    ela_pixels, _ = build_analysis_pixels(recompressed)
    if ela_pixels.width != pixels.width or ela_pixels.height != pixels.height:
        return 0.0

    block_ela = []
    for y in range(min_y, max_y + 1, block_size):
        for x in range(min_x, max_x + 1, block_size):
            mean_val = block_ela_mean(pixels, ela_pixels, page_mask, x, y, block_size)
            if mean_val >= 0:
                block_ela.append(mean_val)

    if len(block_ela) < 4:
        return 0.0
    med = median(block_ela)
    if med <= 0.5:
        return 0.0

    suspicious = sum(1 for v in block_ela if v >= med * 2.5)
    return suspicious / len(block_ela)


# ── Scatter Noise Profile（散点噪声剖面分析）──────────────────────────────────

def is_scatter_noise_profile(patch, std_var, cluster_cover, cluster_ratio):
    if patch >= 0.45 and std_var < 26 and cluster_cover >= 0.28:
        return True
    if patch >= 0.30 and std_var < 24 and cluster_cover < 0.20:
        return True
    if patch >= 0.32 and std_var < 35 and cluster_cover < 0.25:
        return True
    return patch >= 0.36 and std_var < 28 and cluster_cover < 0.22 and cluster_ratio < 0.78


# ── Document Inspection（文档版式、纸张区域、文字块检查）──────────────────────

def inspect_document(pixels, pil_image):
    h, w = pixels.gray.shape
    page_mask = np.zeros((h, w), dtype=bool)

    min_x, min_y = w, h
    max_x, max_y = -1, -1
    page_pixels = 0

    r = pixels.rgb[:, :, 0]
    g = pixels.rgb[:, :, 1]
    b = pixels.rgb[:, :, 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    brightness = mx / 255.0
    with np.errstate(divide='ignore', invalid='ignore'):
        saturation = np.where(mx == 0, 0.0, (mx - mn).astype(np.float64) / mx.astype(np.float64))
    paper = (brightness >= 0.58) & (saturation <= 0.28)
    page_mask = paper

    page_pixels = int(np.sum(page_mask))
    if page_pixels == 0:
        return {
            "page_coverage": 0.0, "page_component_count": 0,
            "background_noise_variance": 0.0, "suspicious_patch_ratio": 0.0,
            "suspicious_cluster_ratio": 0.0, "largest_cluster_coverage": 0.0,
            "text_band_variance": 0.0, "lbp_inconsistency_ratio": 0.0,
            "gradient_incoherence_ratio": 0.0, "noise_inconsistency_ratio": 0.0,
            "ela_anomaly_ratio": 0.0, "risk_score": 0, "findings": [],
        }

    ys, xs = np.where(page_mask)
    min_x, min_y = int(np.min(xs)), int(np.min(ys))
    max_x, max_y = int(np.max(xs)), int(np.max(ys))

    page_coverage = page_pixels / (w * h)

    block_size = max(24, min(w, h) // 28)

    blocks = []
    for y in range(min_y, max_y + 1, block_size):
        for x in range(min_x, max_x + 1, block_size):
            bm = build_block_metric(pixels, page_mask, x, y, block_size)
            if bm["coverage"] >= 0.65:
                blocks.append(bm)

    if not blocks:
        return {
            "page_coverage": rd(page_coverage), "page_component_count": count_page_components(page_mask, min_x, min_y, max_x, max_y),
            "background_noise_variance": 0.0, "suspicious_patch_ratio": 0.0,
            "suspicious_cluster_ratio": 0.0, "largest_cluster_coverage": 0.0,
            "text_band_variance": 0.0, "lbp_inconsistency_ratio": 0.0,
            "gradient_incoherence_ratio": 0.0, "noise_inconsistency_ratio": 0.0,
            "ela_anomaly_ratio": 0.0, "risk_score": 0, "findings": ["检测到的纸张区域过于零散，无法进行篡改分析。"],
        }

    mean_std = average_std(blocks)
    std_variance = variance_of_std(blocks, mean_std)
    suspicious_blocks, effective, anomaly_ratio = calculate_block_anomaly_ratio(blocks, mean_std)
    cluster_metrics = calculate_cluster_metrics(suspicious_blocks, block_size, page_pixels)
    text_band_variance = estimate_text_band_variance(pixels, page_mask, min_x, min_y, max_x, max_y)
    page_component_count = count_page_components(page_mask, min_x, min_y, max_x, max_y)

    lbp_inconsistency = calculate_lbp_inconsistency(pixels, page_mask, blocks, block_size)
    gradient_incoherence = calculate_gradient_incoherence(pixels, page_mask, blocks, block_size)
    noise_inconsistency = calculate_noise_inconsistency(pixels, page_mask, min_x, min_y, max_x, max_y, block_size)
    ela_anomaly = calculate_ela_anomaly(pil_image, pixels, page_mask, min_x, min_y, max_x, max_y, block_size)

    scatter_noise = is_scatter_noise_profile(anomaly_ratio, std_variance, cluster_metrics["largest_cluster_coverage"], cluster_metrics["cluster_ratio"])

    score = 0
    findings = []

    if std_variance >= 95:
        score += 18
        findings.append(f"底纹方差显著偏高 ({rd(std_variance)})。")
    elif std_variance >= 55:
        score += 10
        findings.append(f"底纹一致性存在异常 ({rd(std_variance)})。")

    if anomaly_ratio >= 0.16:
        score += 28
        findings.append("存在多个局部区域疑似覆盖修改。")
    elif anomaly_ratio >= 0.08:
        score += 18
        findings.append("存在部分局部区域与周边底纹不一致。")

    if text_band_variance >= 0.08:
        score += 18
        findings.append("文本区域分布存在明显异常波动。")
    elif text_band_variance >= 0.045:
        score += 10
        findings.append("文本区域分布存在一定不一致。")

    if page_component_count >= 2:
        score -= 12
        findings.append("检测到多页或书页拍摄场景，降低局部篡改判定权重。")

    if scatter_noise:
        score = max(0, score - 18)
        findings.append("散射噪声画像，降低局部篡改判定权重。")

    result = {
        "page_coverage": rd(page_coverage),
        "page_component_count": page_component_count,
        "background_noise_variance": rd(std_variance),
        "suspicious_patch_ratio": rd(anomaly_ratio),
        "suspicious_cluster_ratio": rd(cluster_metrics["cluster_ratio"]),
        "largest_cluster_coverage": rd(cluster_metrics["largest_cluster_coverage"]),
        "text_band_variance": rd(text_band_variance),
        "lbp_inconsistency_ratio": rd(lbp_inconsistency),
        "gradient_incoherence_ratio": rd(gradient_incoherence),
        "noise_inconsistency_ratio": rd(noise_inconsistency),
        "ela_anomaly_ratio": rd(ela_anomaly),
        "scatter_noise_profile": scatter_noise,
        "risk_score": clamp_score(score),
        "findings": findings,
    }
    return result


# ── Metadata Inspection（EXIF/元数据：软件名、AIGC 标签、时间戳等）────────────

def inspect_metadata(image_bytes, image_type):
    result = {"exif_present": False, "make": None, "model": None, "software": None,
              "date_time": None, "date_time_original": None, "gps_present": False,
              "user_comment": None, "jfif": False, "adobe": False,
              "suspicious_software": False, "suspicious_aigc_metadata": False,
              "risk_score": 0, "findings": []}

    findings = []

    if image_type == TYPE_JPEG:
        seg = parse_jpeg_segments(image_bytes)
        result["jfif"] = seg["jfif"]
        result["adobe"] = seg["adobe"]
        exif = parse_exif(seg["exif_payload"])
        result["exif_present"] = exif["exif_present"]
        result["make"] = exif["make"]
        result["model"] = exif["model"]
        result["software"] = exif["software"]
        result["date_time"] = exif["date_time"]
        result["date_time_original"] = exif["date_time_original"]
        result["gps_present"] = exif["gps_present"]
        result["user_comment"] = exif["user_comment"]

        score = 0
        if not result["exif_present"]:
            score += 22
            findings.append("JPEG 图片未检测到 EXIF 元数据。")

        sw = result["software"]
        if sw:
            findings.append(f"软件元数据：{sw}")
            sw_lower = sw.lower()
            for kw in EDIT_SOFTWARE_KEYWORDS:
                if kw in sw_lower:
                    score += 40
                    result["suspicious_software"] = True
                    findings.append("编辑工具标记疑似表明图片经过后期处理或 AI 编辑。")
                    break

        uc = result["user_comment"]
        if uc:
            uc_lower = uc.lower()
            for kw in AIGC_METADATA_KEYWORDS:
                if kw.lower() in uc_lower:
                    score += 55
                    result["suspicious_aigc_metadata"] = True
                    findings.append("JPEG EXIF UserComment 命中 AIGC/内容生产签名元数据。")
                    break

        result["risk_score"] = clamp_score(score)

    elif image_type == TYPE_PNG:
        png_text = parse_png_text_chunks(image_bytes)
        exif = parse_exif(parse_png_exif_payload(image_bytes))
        result["exif_present"] = exif["exif_present"]
        result["software"] = png_text.get("Software") or exif["software"]
        result["date_time"] = png_text.get("Creation Time") or exif["date_time"]
        result["date_time_original"] = exif["date_time_original"]
        result["make"] = exif["make"]
        result["model"] = exif["model"]
        result["gps_present"] = exif["gps_present"]
        result["user_comment"] = exif["user_comment"]

        score = 0
        sw = result["software"]
        if sw:
            findings.append(f"PNG 软件元数据：{sw}")
            sw_lower = sw.lower()
            for kw in EDIT_SOFTWARE_KEYWORDS:
                if kw in sw_lower:
                    score += 35
                    result["suspicious_software"] = True
                    findings.append("PNG 编辑工具标记疑似表明该图片为生成图或编辑后输出。")
                    break

        uc = result["user_comment"]
        if uc:
            findings.append("PNG EXIF UserComment 已检测到内容。")
            uc_lower = uc.lower()
            for kw in AIGC_METADATA_KEYWORDS:
                if kw.lower() in uc_lower:
                    score += 55
                    result["suspicious_aigc_metadata"] = True
                    findings.append("命中 AIGC/内容生产签名元数据。")
                    break

        aigc_text = png_text.get("Aigc")
        if aigc_text:
            findings.append("检测到 PNG Aigc 文本元数据块。")
            aigc_lower = aigc_text.lower()
            for kw in AIGC_METADATA_KEYWORDS:
                if kw.lower() in aigc_lower:
                    score += 55
                    result["suspicious_aigc_metadata"] = True
                    findings.append("PNG Aigc 文本块命中 AIGC/内容生产签名元数据。")
                    break

        if not png_text:
            findings.append("PNG 图片未检测到文本元数据。")

        result["risk_score"] = clamp_score(score)

    else:
        findings.append(f"当前图片类型的元数据检测能力有限：{image_type}")

    result["findings"] = findings
    return result


# ── Main Detection（主检测流程：串联各子模块并汇总风险分）────────────────────

def compute_tamper_index(document, metadata, is_screenshot=False):
    std_var = document.get("background_noise_variance", 0)
    gradient = document.get("gradient_incoherence_ratio", 0)
    patch = document.get("suspicious_patch_ratio", 0)
    cluster_cover = document.get("largest_cluster_coverage", 0)
    lbp = document.get("lbp_inconsistency_ratio", 0)
    text_band = document.get("text_band_variance", 0)

    std_score = scale_linear(std_var, 18, 52, 0, 38)
    grad_score = scale_linear(gradient, 0.10, 0.45, 0, 28)
    std_patch_ratio = std_var / max(0.05, patch) if patch > 0 else 0
    ratio_score = scale_linear(std_patch_ratio, 45, 110, 0, 18) if std_var >= 18 else 0
    cluster_score = scale_linear(cluster_cover * patch, 0.02, 0.22, 0, 14)
    lbp_score = scale_linear(lbp, 0.06, 0.18, 0, 10) if patch >= 0.06 else 0
    text_band_score = scale_linear(text_band, 0.005, 0.012, 0, 6) if patch >= 0.06 else 0
    meta_bonus = 25 if (metadata.get("suspicious_software") or metadata.get("suspicious_aigc_metadata")) else 0

    scatter_noise = document.get("scatter_noise_profile", False)
    index = int(round(std_score + grad_score + ratio_score + cluster_score + lbp_score + text_band_score + meta_bonus))
    if scatter_noise:
        index = max(0, index - 12)
    if is_screenshot:
        index = max(0, index - 2)
    return clamp_score(index)


def compute_tamper_risk(document):
    patch = document.get("suspicious_patch_ratio", 0)
    std_var = document.get("background_noise_variance", 0)
    cluster_cover = document.get("largest_cluster_coverage", 0)
    lbp = document.get("lbp_inconsistency_ratio", 0)
    gradient = document.get("gradient_incoherence_ratio", 0)
    text_band = document.get("text_band_variance", 0)
    noise_inc = document.get("noise_inconsistency_ratio", 0)
    ela = document.get("ela_anomaly_ratio", 0)

    score = 0
    if patch >= 0.40:
        score += 20
    elif patch >= 0.22:
        score += 12
    elif patch >= 0.10:
        score += 6

    if std_var >= 50:
        score += 28
    elif std_var >= 30:
        score += 14
    elif std_var >= 18:
        score += 6

    if cluster_cover >= 0.50:
        score += 14
    elif cluster_cover >= 0.22:
        score += 8

    if lbp >= 0.18:
        score += 16
    elif lbp >= 0.12:
        score += 8

    if gradient >= 0.16:
        score += 14
    elif gradient >= 0.12:
        score += 7

    std_patch = std_var / max(0.05, patch) if patch > 0 else 0
    if std_patch >= 85:
        score += 12

    if text_band >= 0.009:
        score += 8

    if noise_inc >= 0.25:
        score += 6

    if ela >= 0.20:
        score += 6

    if document.get("scatter_noise_profile", False):
        score = max(0, score - 20)

    return clamp_score(score)


def compute_compression_risk(image_type, jpeg_quality, blockiness):
    if image_type != TYPE_JPEG:
        return 0
    score = 0
    if jpeg_quality is not None and jpeg_quality > 0:
        if jpeg_quality <= 55:
            score += 22
        elif jpeg_quality <= 70:
            score += 10
    if blockiness >= 1.35:
        score += 24
    elif blockiness >= 1.2:
        score += 12
    return clamp_score(score)


def is_screenshot_material(screenshot, image_type, file_name=""):
    score_val = 0
    if screenshot.get("text_row_ratio", 0) >= 0.10:
        score_val += 1
    if screenshot.get("flat_region_ratio", 0) >= 0.25:
        score_val += 1
    if screenshot.get("nearest_screen_ratio_delta", 1) <= 0.10:
        score_val += 1
    if image_type == TYPE_PNG:
        score_val += 1
    lower = file_name.lower()
    if "截图" in lower or "企业微信" in lower or "screenshot" in lower:
        score_val += 2
    return score_val >= 3


def count_pending_signals(document):
    signals = 0
    if document.get("background_noise_variance", 0) >= 26:
        signals += 1
    if document.get("gradient_incoherence_ratio", 0) >= 0.10:
        signals += 1
    if document.get("suspicious_patch_ratio", 0) >= 0.10:
        signals += 1
    if document.get("lbp_inconsistency_ratio", 0) >= 0.06:
        signals += 1
    if document.get("largest_cluster_coverage", 0) >= 0.10:
        signals += 1
    if document.get("noise_inconsistency_ratio", 0) >= 0.20:
        signals += 1
    if document.get("ela_anomaly_ratio", 0) >= 0.15:
        signals += 1
    if document.get("text_band_variance", 0) >= 0.007:
        signals += 1
    std_patch = document.get("background_noise_variance", 0) / max(0.05, document.get("suspicious_patch_ratio", 0.001))
    if std_patch >= 45 and document.get("suspicious_patch_ratio", 0) >= 0.08:
        signals += 1
    return signals


def decide(metadata, document, compression_risk, screenshot, image_type, file_name):
    findings = []
    evidence = 0

    patch = document.get("suspicious_patch_ratio", 0)
    std_var = document.get("background_noise_variance", 0)
    cluster = document.get("suspicious_cluster_ratio", 0)
    cluster_cover = document.get("largest_cluster_coverage", 0)
    text_band = document.get("text_band_variance", 0)
    lbp = document.get("lbp_inconsistency_ratio", 0)
    gradient = document.get("gradient_incoherence_ratio", 0)
    noise_inc = document.get("noise_inconsistency_ratio", 0)
    ela = document.get("ela_anomaly_ratio", 0)
    scatter_noise = document.get("scatter_noise_profile", False)

    if scatter_noise:
        findings.append("可疑块呈散射分布且底纹方差偏低，更符合微信截图压缩噪声（已作扣分处理）。")

    if metadata.get("suspicious_software") or metadata.get("suspicious_aigc_metadata"):
        evidence += 3
        findings.append("元数据命中编辑工具或 AIGC 签名。")

    if std_var >= 50:
        evidence += 2
        findings.append(f"底纹方差显著偏高 ({rd(std_var)})。")
    elif std_var >= 30:
        findings.append(f"底纹方差值 {rd(std_var)}。")

    std_patch_ratio = std_var / max(0.05, patch) if patch > 0 else 0
    if std_patch_ratio >= 85 and patch >= 0.22:
        evidence += 2
        findings.append(f"底纹方差相对可疑块占比偏高 (ratio={rd(std_patch_ratio)})。")

    if patch >= 0.40 and cluster_cover >= 0.22 and std_var >= 18:
        evidence += 2
        findings.append(f"高比例可疑块局部聚集且底纹有差异 (patch={rd(patch)}, cover={rd(cluster_cover)})。")
    elif patch >= 0.22 and cluster_cover >= 0.50 and std_var >= 18:
        evidence += 2
        findings.append("可疑块聚集明显且底纹有差异。")
    elif patch >= 0.22 and std_var >= 30:
        evidence += 1
        findings.append("可疑块与底纹方差同时偏高。")

    if lbp >= 0.18 and patch >= 0.10:
        evidence += 2
        findings.append(f"LBP 纹理与邻域不一致块偏多 ({rd(lbp)})。")
    elif lbp >= 0.12 and patch >= 0.22:
        evidence += 1

    if gradient >= 0.16 and patch >= 0.10:
        evidence += 2
        findings.append(f"梯度方向断层明显 ({rd(gradient)})。")
    elif gradient >= 0.12 and patch >= 0.22 and std_var >= 18:
        evidence += 1

    if patch >= 0.10 and cluster >= 0.65 and std_var >= 24:
        evidence += 1
        findings.append(f"可疑块高度集中于局部区域 (clusterRatio={rd(cluster)})。")

    if text_band >= 0.009 and patch >= 0.10:
        evidence += 1
        findings.append(f"文本带波动异常 ({rd(text_band)})。")

    if image_type == TYPE_JPEG and compression_risk >= 45 and patch >= 0.10:
        evidence += 1
        findings.append("JPEG 压缩痕迹与局部异常并存。")

    if noise_inc >= 0.25 and patch >= 0.10:
        evidence += 1
        findings.append(f"噪声不一致性偏高 ({rd(noise_inc)})。")

    if ela >= 0.20 and patch >= 0.10:
        evidence += 1
        findings.append(f"ELA 残差异常偏高 ({rd(ela)})。")

    pending_signals = count_pending_signals(document)
    screenshot_material = is_screenshot_material(
        {**screenshot, "page_coverage": document.get("page_coverage", 0)},
        image_type, file_name
    )

    tamper_index = compute_tamper_index(document, metadata, is_screenshot=screenshot_material)
    forgery_score = max(compute_tamper_risk(document), tamper_index)
    if metadata.get("suspicious_software") or metadata.get("suspicious_aigc_metadata"):
        forgery_score = max(forgery_score, 90)

    # ── Decision Logic ──
    # Guard: high gradient + high noise_inconsistency + very high std/patch ratio
    # indicates global uniform noise (complex document photo), not localized tampering
    uniform_noise = (
        gradient >= 0.40
        and noise_inc >= 0.85
        and patch >= 0.05
        and (std_var / max(patch, 0.01)) >= 200
    )

    # For screenshots: high gradient with moderate std_var is likely photo artifact
    photo_artifact = screenshot_material and gradient >= 0.4 and std_var < 45

    # Combined override: images where strong signals are likely natural, not tampered
    noise_override = uniform_noise or photo_artifact

    # Strong single-signal evidence (bypasses screenshot guard)
    forged_primary = (
        metadata.get("suspicious_software") or metadata.get("suspicious_aigc_metadata")
        or (std_var >= 52 and not noise_override)
        or (patch >= 0.40 and std_var >= 44 and cluster_cover >= 0.18 and not noise_override)
        or (patch >= 0.30 and std_var >= 44 and cluster_cover >= 0.12 and not noise_override)
        or (gradient >= 0.42 and patch >= 0.22 and std_var >= 40 and not noise_override)
    )

    # For screenshot material (WeChat screenshots), require stronger evidence
    # to avoid false positives from compression/texture/photography artifacts
    if screenshot_material:
        forged_by_index = tamper_index >= 54 and (
            not scatter_noise or (std_var >= 36 or gradient >= 0.30)
        ) and not (photo_artifact and tamper_index < 80) and not uniform_noise
        forged_by_combination = (std_var >= 40 and patch >= 0.12 and gradient >= 0.18
                                 and tamper_index >= 48) and not photo_artifact and not uniform_noise
        forged_by_multi = (pending_signals >= 4 and tamper_index >= 42
                           and gradient >= 0.14) and not photo_artifact and not uniform_noise
    else:
        # Non-screenshot: use lower thresholds to catch borderline tampering
        forged_by_index = tamper_index >= 46 and (
            not scatter_noise or (std_var >= 32 or gradient >= 0.26)
        ) and not uniform_noise
        forged_by_combination = (
            (std_var >= 36 or std_patch_ratio >= 70)
            and patch >= 0.08
            and (gradient >= 0.16 or cluster_cover >= 0.08)
            and ((tamper_index >= 38 and std_var >= 34)
                 or (tamper_index >= 36 and gradient >= 0.12)
                 or (tamper_index >= 34 and evidence >= 1 and pending_signals >= 1))
        )
        forged_by_multi = (
            pending_signals >= 3
            and tamper_index >= 34
            and (gradient >= 0.10 or lbp >= 0.06 or cluster_cover >= 0.08)
        )

    forged = forged_primary or forged_by_index or forged_by_combination or forged_by_multi

    is_clean_screenshot = not forged and screenshot_material and tamper_index < 30 and evidence == 0 and patch < 0.08 and pending_signals <= 1
    is_pending = not forged and not is_clean_screenshot and (
        (tamper_index >= 32 and pending_signals >= 2)
        or tamper_index >= 40
        or (patch >= 0.10 and std_var >= 12 and pending_signals >= 1)
        or (evidence >= 1 and tamper_index >= 26)
        or (scatter_noise and patch >= 0.20)
        or (screenshot_material and tamper_index >= 22 and pending_signals >= 1)
        or (screenshot_material and tamper_index < 30 and evidence == 0 and (patch >= 0.08 or pending_signals >= 1))
    )

    if forged:
        review_status = "有伪造"
        conclusion = "检测到多处篡改相关信号，建议人工重点复核。"
        risk_labels = ["有伪造"]
        if patch >= 0.10:
            risk_labels.append("疑似局部篡改")
    elif is_pending:
        review_status = "待确认"
        conclusion = "存在部分可疑信号但未达强判定阈值，建议人工确认。"
        risk_labels = ["待确认"]
        if not findings:
            findings.append(f"边界样本：tamperIndex={tamper_index}, patch={rd(patch)}, stdVar={rd(std_var)}, "
                            f"lbp={rd(lbp)}, gradient={rd(gradient)}, clusterCover={rd(cluster_cover)}")
    elif is_clean_screenshot:
        review_status = "截图"
        conclusion = "材料呈现典型微信/屏幕截图特征，未检测到明显篡改痕迹。"
        risk_labels = ["截图"]
    else:
        review_status = "无伪造"
        conclusion = "未检测到明显篡改痕迹。"
        risk_labels = ["无伪造"]

    if not is_clean_screenshot and (screenshot.get("flat_region_ratio", 0) >= 0.40 or screenshot.get("text_row_ratio", 0) >= 0.06):
        risk_labels.append("来源可能为截图/微信转发")

    return {
        "tamper_index": tamper_index,
        "forgery_score": forgery_score,
        "tamper_evidence_count": evidence,
        "review_status": review_status,
        "conclusion": conclusion,
        "risk_labels": risk_labels,
        "findings": findings,
    }


# ── Main Entry Point（命令行入口：解析参数、调用检测、打印 JSON）──────────────

def analyze(image_path_or_url):
    img, image_bytes = read_image_from_path(image_path_or_url)
    image_type = detect_image_type(image_bytes, os.path.basename(image_path_or_url))
    pixels, (orig_w, orig_h) = build_analysis_pixels(img)

    result = AnalysisResult()
    result.image_path = image_path_or_url
    result.image_type = image_type
    result.file_size = len(image_bytes)
    result.width = orig_w
    result.height = orig_h

    metadata = inspect_metadata(image_bytes, image_type)
    result.metadata = metadata

    if image_type == TYPE_JPEG:
        seg = parse_jpeg_segments(image_bytes)
        jpeg_quality = estimate_jpeg_quality(seg["quantization_tables"])
        blockiness = calculate_blockiness(pixels)
    else:
        jpeg_quality = None
        blockiness = 0.0

    compression_risk = compute_compression_risk(image_type, jpeg_quality, blockiness)

    visual = inspect_visual(pixels)
    local = inspect_local(pixels)
    screenshot = inspect_screenshot(pixels, visual)
    document = inspect_document(pixels, img)

    result.visual = visual
    result.local = local
    result.screenshot = screenshot
    result.document = document

    all_findings = []
    all_findings.extend(metadata.get("findings", []))
    all_findings.extend(visual.get("findings", []))
    all_findings.extend(local.get("findings", []))
    all_findings.extend(screenshot.get("findings", []))
    all_findings.extend(document.get("findings", []))

    decision = decide(metadata, document, compression_risk, screenshot, image_type,
                      os.path.basename(image_path_or_url))

    result.tamper_index = decision["tamper_index"]
    result.forgery_score = decision["forgery_score"]
    result.tamper_evidence_count = decision["tamper_evidence_count"]
    result.review_status = decision["review_status"]
    result.conclusion = decision["conclusion"]
    result.risk_labels = decision["risk_labels"]
    result.findings = all_findings + decision["findings"]

    result.suspicious = decision["review_status"] == "有伪造"
    result.suspected_edited = result.suspicious or decision["review_status"] == "待确认"
    result.suspected_screenshot = screenshot.get("suspected_screenshot", False)

    overall = max(
        decision["forgery_score"],
        document.get("risk_score", 0),
        screenshot.get("risk_score", 0),
        compression_risk,
    )
    result.overall_risk_score = overall

    return result


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Detect image forgery/tampering")
    parser.add_argument("image_positional", nargs="?", help="Image path or URL (positional)")
    parser.add_argument("--image", dest="image", help="Image path or URL")
    parser.add_argument("--url", dest="url", help="Alias for image URL")
    args = parser.parse_args()

    path = args.image or args.url or args.image_positional
    if not path:
        print(json.dumps({"error": "Missing required argument: --image or image URL"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    try:
        result = analyze(path)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    except Exception as e:
        error = {
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
        print(json.dumps(error, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
