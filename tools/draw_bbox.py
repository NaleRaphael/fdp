from argparse import ArgumentParser

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pdfminer.high_level import extract_pages


def bbox_to_rect_params(bbox, offset=None):
    """Convert values in bbox tuple to the format that
    `matplotlib.patches.Rectangle()` takes.

    Parameters
    ----------
    bbox : tuple (containing 4 float values)
        A tuple of bounding box in the format of `(x1, y1, x2, y2)`
        (bottom-left and top-right corner).

    Returns
    -------
    (x1, y1), width, height : float
        Coordinate of bottom-left corner and width/height of bounding box.
    """
    x1, y1, width, height = *(bbox[:2]), bbox[2]-bbox[0], bbox[3]-bbox[1]
    if offset:
        if len(offset) != 2:
            raise ValueError('`offset` should contains only 2 values: (x, y)')
        return (x1 + offset[0], y1 + offset[1]), width, height
    else:
        return (x1, y1), width, height


def _draw_single_page_bboxes(page, fig, ax, page_offset=None, show_annotation=False):
    ax.add_patch(
        patches.Rectangle(
            *bbox_to_rect_params(page.bbox, offset=page_offset),
            linewidth=1, edgecolor='k', facecolor='none'
        )
    )

    for i, element in enumerate(page):
        ax.add_patch(
            patches.Rectangle(
                *bbox_to_rect_params(element.bbox, offset=page_offset),
                linewidth=1, edgecolor='g', facecolor='none'
            )
        )
        # Show the order of this bbox
        if show_annotation:
            (x1, y1), *_ = bbox_to_rect_params(element.bbox, offset=page_offset)
            ax.text(x1, y1, str(i))


VALID_ORIENTATION = ['vertical', 'horizontal']

def draw_page_bboxes(pages, orientation='vertical', page_spacing=20, show_annotation=False):
    """Draw bounding boxes of all elements in pages.

    Parameters
    ----------
    pages : list of pdfminer.layout.LTPage
    orientation : string, optional
        Orientation of pages.
    page_spacing : int
        Spacing between drawn bounding boxes of pages.

    Returns
    -------
    fig : matplotlib.figure.Figure
    ax : matplotlib.axes._subplots.AxesSubplot
    """
    if orientation not in VALID_ORIENTATION:
        raise ValueError(f'`orientation` should be one of {VALID_ORIENTATION}')

    fig, ax = plt.subplots()
    page_offset = (0, 0)

    for page in pages:
        _draw_single_page_bboxes(
            page, fig, ax, page_offset=page_offset, show_annotation=show_annotation
        )

        if orientation == 'vertical':
            page_offset = (0, page_offset[1] - (page.height + page_spacing))
        else:
            page_offset = (page.width + page_offset[0] + page_spacing, 0)

    ax.axis('equal')
    return fig, ax


USAGE = """
Draw bounding box of elements in a PDF file.

$ python draw_bbox.py FILE_NAME --page_start=PAGE_START [--page_end=PAGE_END]
    [--orientation=["vertical"|"horizontal"]] [--show_annotation]
"""

def parse_args():
    parser = ArgumentParser(usage=USAGE)
    parser.add_argument(
        'fn', type=str, metavar='FILE_NAME', help='Input PDF file.'
    )
    parser.add_argument(
        '--page_start', type=int, required=True,
        help='First page to draw.'
    )
    parser.add_argument(
        '--page_end', type=int, default=-1,
        help='Last page to draw.'
    )
    parser.add_argument(
        '--orientation', type=str, default='vertical',
        help='Orientation of pages to draw.'
    )
    parser.add_argument(
        '--show_annotation', action='store_true',
        help=('Show annotation of the order of bounding boxes resolved by'
        'layout algorithm.')
    )
    return parser.parse_args()


def main():
    args = parse_args()

    fn = args.fn
    if args.page_end == -1:
        page_numbers = [args.page_start - 1]
    else:
        page_numbers = list(range(args.page_start - 1, args.page_end))

    page_layouts = extract_pages(fn, page_numbers=page_numbers)

    fig, ax = draw_page_bboxes(
        page_layouts, orientation=args.orientation,
        show_annotation=args.show_annotation
    )
    plt.show()


if __name__ == "__main__":
    main()

