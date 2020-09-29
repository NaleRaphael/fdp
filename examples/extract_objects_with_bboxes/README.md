# Example: extract PDF objects with bounding boxes

In this example, it shows how to extract PDF objects with bounding boxes using facilities implemented in submodule `fdp.pdf`.

Currently, there are two approaches:
1. Aggregate text according to existing source of parsed text
2. Extract text using algorithm implemented in `pdfminer.six`

The reason why there is a need to analyze content with another text source (approach 1) is that the string parser in `pdfminer.six` might failed to parse content correctly.

Hence that this approach give us a chance to extract text content with the advantage of the layout algorithm provided by `pdfminer.six`, but we can still replaced those matched text by our own source if we have a better string parser.

But note that **the first approach is not stable** currently.

## Usage
### Basic usage
Just execute the script `main.py` in this folder, and it will download required tool script (`pdfminer.six/pdf2txt.py`) and data (a PDF file) automatically. Then you can checkout the difference between those 2 output files `output1.json` and `output2.json`.

```bash
$ python main.py
```

### Checkout bounding boxes of PDF objects
You can also checkout the bounding boxes of text/non-text objects stored in `PageData` by `fdp.drawer.draw_pdf_objects()` method.

```python
# file: main.py
from fdp.drawer import draw_pdf_objects     # <- add this

# ...

def main():
    page_numbers = [0, 1, 2]
    pdf = PDF.load(str(FN_PDF), page_numbers=page_numbers)

    # ...

    page_data_list2 = []
    for page in pdf.pages:
        page_data = PageData.load_from_page(page)

        draw_pdf_objects(page, page_data.text_groups, show_annotation=True)  # <- add this

        # or you can checkout those bounding boxes of non-text objects
        # draw_pdf_objects(page, page_data.non_text_groups, show_annotation=True)
```

## Content of a output file
Currently, data are stored in page-based structure (see also `fdp.pdf.PageData`). And those PDF objects are classified into two main categories:

- text object: `<LTTextBox>`, `<LTTextBoxHorizontal>`, ...
- non-text object: `<LTTextFigure>`, `<LTTextCurve>`, ...

Note that these objects with prefix `LT` are defined in `pdfminer.layout`, and these objects will be converted into `PDFObject` in order to make them JSON-serializable. Although we cannot convert them from `PDFObject` back to those classes defined in `pdfminer.layout`, there are four attributes stored to make them identifiable:

- index: order of this object being resolved by layout algorithm
- bbox: bounding box (4 float values, coordinates of top-left and bottom-right corner)
- type: string of original type
- content: text (if it's a text-like object) or None (if it's a non-text object)

Therefore, content of the output file (.json) will look like this:

```raw
{
    {
        # page 1
        "pageid": 1,
        "text_groups": [
            {
                "index": 0,
                "bbox": [...],
                "type": ...,
                "content": ...
            },
            ...
        ],
        "non_text_groups": [...]
    },
    {
        # page 2
        "pageid": 2,
        "text_groups": [...],
        "non_text_groups": [...],
    },
    # ...
}
```



