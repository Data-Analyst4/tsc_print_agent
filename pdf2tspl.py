#!/usr/bin/env python3

import tempfile
import subprocess
import dataclasses
import os

@dataclasses.dataclass
class Image:
    width: int
    height: int
    data: bytes


def _get_pixel(data, row_bytes, x, y):
    byte = data[y * row_bytes + (x // 8)]
    bit = 7 - (x % 8)
    return (byte >> bit) & 1


def _set_pixel(data, row_bytes, x, y):
    data[y * row_bytes + (x // 8)] |= 1 << (7 - (x % 8))


def rotate_image(image, degrees):
    degrees %= 360
    if degrees == 0:
        return image
    if degrees not in (90, 180, 270):
        raise ValueError(f"unsupported rotation: {degrees}")

    src_w = image.width
    src_h = image.height
    src_row_bytes = (src_w + 7) // 8

    if degrees in (90, 270):
        dst_w, dst_h = src_h, src_w
    else:
        dst_w, dst_h = src_w, src_h

    dst_row_bytes = (dst_w + 7) // 8
    dst = bytearray(dst_row_bytes * dst_h)

    for y in range(src_h):
        for x in range(src_w):
            if not _get_pixel(image.data, src_row_bytes, x, y):
                continue

            if degrees == 90:
                dst_x = src_h - 1 - y
                dst_y = x
            elif degrees == 180:
                dst_x = src_w - 1 - x
                dst_y = src_h - 1 - y
            else:  # 270
                dst_x = y
                dst_y = src_w - 1 - x

            _set_pixel(dst, dst_row_bytes, dst_x, dst_y)

    return Image(dst_w, dst_h, bytes(dst))

def convert_pdf(pdfname, args=[]):
    # Use current directory for temp file instead of system temp
    temp_pbm = "temp_convert.pbm"
    try:
        cmd = [r"C:\poppler\poppler-25.07.0\Library\bin\pdftoppm.exe", "-mono", "-singlefile"] + args + [pdfname, temp_pbm.removesuffix('.pbm')]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"pdftoppm failed: {result.stderr}")
        
        with open(temp_pbm, 'rb') as pbmfile:
            header = pbmfile.readline()
            if header.strip() != b'P4':
                raise ValueError(f"unrecognised image format: {header}")
            width_height = pbmfile.readline().decode('ascii')
            data = bytes(x ^ 0xff for x in pbmfile.read())
    finally:
        if os.path.exists(temp_pbm):
            os.remove(temp_pbm)

    width, height = map(int, width_height.strip().split())
    return Image(width, height, data)

def convert_pdf_scaled(pdfname, max_width, max_height):
    im = convert_pdf(pdfname)
    aspect = im.width / im.height
    max_aspect = max_width / max_height

    if aspect < max_aspect:
        max_width = int(max_height * aspect) - 1
    else:
        # pdftoppm tends to make it 1px too wide
        max_width -= 1
        max_height = int(max_width / aspect)

    args = ['-scale-to-x', str(max_width), '-scale-to-y', str(max_height)]
    im = convert_pdf(pdfname, args)

    assert im.width <= max_width + 1
    assert im.height <= max_height

    return im

def pdf2tspl(
    filename,
    labelwidth_mm=100,
    labelheight_mm=150,
    dpi=203.2,
    rotate=0,
    x_offset_dots=0,
    y_offset_dots=0,
):
    labelwidth = int(round(labelwidth_mm / 25.4 * dpi))
    labelheight = int(round(labelheight_mm / 25.4 * dpi))

    rotate = rotate % 360
    if rotate in (90, 270):
        image = convert_pdf_scaled(filename, labelheight, labelwidth)
    else:
        image = convert_pdf_scaled(filename, labelwidth, labelheight)
    image = rotate_image(image, rotate)

    paste_x = (labelwidth - image.width) // 2 + int(x_offset_dots)
    paste_y = (labelheight - image.height) // 2 + int(y_offset_dots)
    row_bytes = (image.width + 7) // 8

    tspl = b"\r\n\r\nSIZE %d mm,%d mm\r\nCLS\r\nBITMAP %d,%d,%d,%d,0," % (labelwidth_mm, labelheight_mm, paste_x, paste_y, row_bytes, image.height)
    tspl += image.data
    tspl += b"\r\nPRINT 1,1\r\n"
    return tspl

if __name__ == "__main__":
    import argparse
    import sys
    parser = argparse.ArgumentParser(description='Convert a PDF to TSPL to send to a label printer.')
    parser.add_argument('pdf_file', help='The PDF to convert.')
    parser.add_argument('tspl_file', help='The file or device to write the TSPL code to. Can be a printer device eg. /dev/usb/lp0, or specify "-" to write to stdout.')

    parser.add_argument('-x', '--width', type=int, default=100, help='The width of the label, in millimetres.')
    parser.add_argument('-y', '--height', type=int, default=150, help='The height of the label, in millimetres.')
    parser.add_argument('-d', '--dpi', type=float, default=203.2, help='Resolution of the printer. Defaults to 8 dots per mm (203.2 dpi)')
    parser.add_argument('-r', '--rotate', type=int, choices=[0, 90, 180, 270], default=0, help='Rotate PDF content clockwise before placement.')
    parser.add_argument('--x-offset-dots', type=int, default=0, help='Horizontal placement tweak in printer dots.')
    parser.add_argument('--y-offset-dots', type=int, default=0, help='Vertical placement tweak in printer dots.')
    args = parser.parse_args()

    tspl = pdf2tspl(args.pdf_file,
                    labelwidth_mm=args.width,
                    labelheight_mm=args.height,
                    dpi=args.dpi,
                    rotate=args.rotate,
                    x_offset_dots=args.x_offset_dots,
                    y_offset_dots=args.y_offset_dots)

    if args.tspl_file == '-':
        sys.stdout.buffer.write(tspl)
    else:
        with open(args.tspl_file, 'wb') as fp:
            fp.write(tspl)
