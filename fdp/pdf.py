import pdfminer.layout as pmla
import pdfminer.high_level as pmhl
import rapidfuzz as rf


class PageData(object):
    def __init__(self, pageid, text_groups, non_text_groups, unresolved_groups=None, extra_info=None):
        """
        Parameters
        ----------
        pageid : int
        text_groups : list
            List of `PDFObjects`, and they should be converted from text-like
            objects defined in `<pdfminer.layout>`, e.g. `<LTText>`
        non_text_groups : list
            List of `PDFObjects`, and they should be converted from non-text-like
            objects defined in `<pdfminer.layout>`, e.g. `<LTFigure>`
        unresolved_groups : list
            List of `PDFObjects` that were not able to be resolved by `group_text()`.
        extra_info : dict
            Any other information need to be recorded, should be JSON-serializable.
        """
        if extra_info is not None and not isinstance(extra_info, dict):
            raise TypeError('`extra_info` should be a dict')
        self.pageid = pageid
        self.text_groups = text_groups
        self.non_text_groups = non_text_groups
        self.extra_info = {} if extra_info is None else extra_info

    @classmethod
    def load_from_page(cls, page):
        """Directly load data from a `<LTPage>` object."""
        raise NotImplementedError

    @classmethod
    def from_dict(cls, dict):
        pageid = dict.get('pageid')
        text_groups = [PDFObject.from_dict(v) for v in dict.get('text_groups')]
        non_text_groups = [PDFObject.from_dict(v) for v in dict.get('non_text_groups')]
        extra_info = dict.get('extra_info', {})
        return cls(pageid, text_groups, non_text_groups, extra_info=extra_info)

    def to_dict(self):
        return {
            'pageid': self.pageid,
            'text_groups': [v.to_dict() for v in self.text_groups],
            'non_text_groups': [v.to_dict() for v in self.non_text_groups],
            'extra_info': dict(self.extra_info)
        }


class PDFObject(object):
    def __init__(self, index, bbox, type, content):
        """
        Parameters
        ----------
        index : int
        bbox : list, tuple
            Bounding box of this object in a page.
        type : str
            Type string of this object.
        content : object
        """
        self.index = index
        self.bbox = bbox
        self.type = type
        self.content = content

    @classmethod
    def from_object(cls, index, obj, content=None):
        """Create an instance from object types listed in `pdfminer.layout`.

        If argument `content` is not given, it will be determined by the content
        in given `obj`:
        - If given `obj` is `<LTText>`, content will be the text in it.
        - If not, content will be empty.
        """
        type = obj.__class__.__name__
        if content is None:
            content = obj.get_text() if isinstance(obj, pmla.LTText) else None
        return cls(index, obj.bbox, type, content)

    @classmethod
    def from_dict(cls, dict):
        return cls(dict['index'], dict['bbox'], dict['type'], dict['content'])

    def to_dict(self):
        return {
            'index': self.index,
            'bbox': self.bbox,
            'type': self.type,
            'content': self.content,
        }


class PDF(object):
    def __init__(self, pages):
        """
        Parameters
        ----------
        pages : list
            List of `<pdfminer.layout.LTPage>` objects.
        """
        self.pages = pages

    @classmethod
    def load(
        cls, fn, page_numbers=None, preload=False, reader_kwargs=None,
        **kwargs
    ):
        """Load PDF file.

        Parameters
        ----------
        fn : str
            Filename of PDF.
        page_numbers : list
            Pages to be loaded. (0-indexed)
        preload : bool
            Preload content from all pages.
        reader_kwargs : dict
            Other kwargs for `pdfminer.high_level.extract_pages()`.
        """
        if reader_kwargs:
            reader_kwargs.pop('page_numbers', None)
        else:
            reader_kwargs = {}

        pages = pmhl.extract_pages(
            fn, page_numbers=page_numbers, **reader_kwargs
        )
        if preload:
            pages = list(pages)
        return cls(pages)

    def aggregate_raw_text(self, raw_text, use_raw_text=True):
        """Aggregate lines of text in `raw_text`, which is usaully text content
        of a PDF file parsed by any kind of text parser.

        Parameters
        ----------
        raw_text : list
        use_raw_text : bool
            See also the documentation of `locate_text()`.

        Returns
        -------
        page_data_list : list
            List of `PageData` objects.
        """
        page_data_list = []
        offset = 0

        for page in self.pages:
            index2located, index2object, offset, extra_info = locate_text(
                page, raw_text, offset, use_raw_text=use_raw_text
            )
            output = group_text(index2located, index2object)
            text_object_groups, unresolved_text_objects, non_text_objects = output

            keys = reorder_objects(list(text_object_groups.keys()))
            text_groups = [PDFObject.from_object(i, k, content=text_object_groups[k]) for i, k in enumerate(keys)]
            non_text_groups = [PDFObject.from_object(i, obj) for i, obj in enumerate(non_text_objects)]
            unresolved_groups = [PDFObject.from_object(i, obj) for i, obj in enumerate(unresolved_text_objects)]

            page_data = PageData(
                page.pageid,
                text_groups,
                non_text_groups,
                unresolved_groups=unresolved_groups,
            )
            page_data_list.append(page_data)

        return page_data_list


def make_text_object_mapping(page):
    """Generate mapping of lines of text and PDF objects in a PDF page.

    Since there are usually multiple lines of text in a single paragraph and we
    cannot ensure there won't be duplicate lines in other paragraphs, directly
    making a mapping in the form of `{text: <LTText>}` may lead to data loss
    because of overwritten keys.

    Therefore, here we will create two mappings to solve this problem:
    - `index2text`:
        A mapping of indices and all lines of text in this page. This allowes
        duplicate line of text to exist since we are using indices as key
        instead of strings.
    - `index2object`:
        A mapping of indices and PDF objects in this page. We can use this
        mapping to find out the paragraph where a line of text locates.

    Parameters
    ----------
    page : pdfminer.layout.LTPage
        A single PDF page object.

    Returns
    -------
    index2text : dict
        A dict in the form of `{<int>: <str>}`.
    index2object : dict
        A dict in the form of `{<int>: [<LTItem> or <LTText>]}`.
    """
    index2text = {}
    index2object = {}
    offset = 0

    for i, obj in enumerate(page._objs):
        # For non-text objects, we just push them into dictionary directly
        if not isinstance(obj, pmla.LTText):
            index2object.update({offset: obj})
            offset += 1
            continue

        # Handle hyphens followed by newline character
        text = obj.get_text().replace('-\n', '')

        lines = [line for line in text.splitlines() if line != '']
        index2text.update({idx + offset: line for idx, line in enumerate(lines)})
        index2object.update({idx + offset: obj for idx in range(len(lines))})
        offset += len(lines)
    return index2text, index2object


def locate_text(page, raw_text, offset, patience=10, use_raw_text=True):
    """Find corresponding `<pdfminer.layout>` objects according to lines of text
    in given `raw_text`.

    Parameters
    ----------
    page : `<pdfminer.layout.LTPage>`
    raw_text : list
        List of text parsed from PDF.
    offset : int
        An offset value indicating which line in `raw_text` should be taken as
        the first line for this process.
    patience : int
        If it failed to locate text continuously and times of failure exceeds
        this value, the whole process will be terminated.
    use_raw_text : bool
        If true, value of returned `index2located` will be those strings in
        `raw_text.` (Because the built-in string parser in `pdfminer.six`
        might failed to parse correctly.)

    Returns
    -------
    index2located : dict
        A dict in the form of `{index: string}`. User can find corresponding
        object in `index2object` by the keys of this dict.
    index2object : dict
        A dict in the form of `{index: object defined in <pdfminder.layout>}`.
        Note that there might be mulitple keys (indices) mapping to the same
        object (value), that's because an object might be formed by multiple
        components listed in `index2located`. e.g.
        ```python
        index2located = {1: 'foo\n', 2: 'bar\n', 3: 'buzz\n'}
        index2object = {
            1: <LTTextBox(1) ... 'foo\nbar\nbuzz\n'>,
            2: <LTTextBox(1) ... 'foo\nbar\nbuzz\n'>,
            3: <LTTextBox(1) ... 'foo\nbar\nbuzz\n'>,
        }
        ```
    offset : int
        Updated offset after this process is terminated.
    extra_info : dict
        Any other extra information generated during this process.
    """
    index2text, index2object = make_text_object_mapping(page)

    index2located = {}    # {index: query}
    idx_unresolved_line = []
    cnt_skipped = 0
    cnt_unresolved = 0

    if patience is None:
        patience = len(raw_text)

    for i_raw in range(offset, len(raw_text)):
        if cnt_unresolved > patience:
            break

        query = raw_text[i_raw]
        if query == '\n':
            cnt_skipped += 1
            continue

        # Fuzzy match, returned value will be `List[Tuple[text, score, index]]`
        matches = rf.process.extract(
            query, index2text, scorer=rf.fuzz.ratio, score_cutoff=90
        )

        if len(matches) == 0:
            idx_unresolved_line.append(i_raw)
            cnt_unresolved += 1
        else:
            if len(matches) > 1:
                idx_unresolved_line.append(i_raw)
                cnt_unresolved += 1
                continue

            index = matches[0][2]
            parsed_text = index2text.pop(index)
            if use_raw_text:
                index2located.update({index: query})
            else:
                index2located.update({index: parsed_text})

            # Reset counter
            cnt_unresolved = 0
            cnt_skipped = 0

    offset = i_raw - cnt_unresolved - cnt_skipped
    extra_info = {
        'idx_unresolved_line': idx_unresolved_line,
    }
    return index2located, index2object, offset, extra_info


def group_text(index2located, index2object):
    """Group texts according to their corresponding `<LTText>` objects.

    Parameters
    ----------
    index2located : dict
        A dict in the form of `{index: query}`.
    index2object : dict
        A dict in the form of `{index: object defined in <pdfminder.layout>}`.

    Returns
    -------
    text_object_groups : dict
        A dict in the form of `{<pdfminder.layout.LTText>: str}`. Values of
        this dictionary are grouped text, i.e. a paragraph or a section.
    unresolved_text_objects : list
        List of unresolved text objects which might be "metadata of PDF" /
        "page number" / "text in a table/figure" ... and so on.
    non_text_objects : list
        List of non-text objects.
    """
    object_set = set(index2object.values())
    object_groups = {obj: [] for obj in object_set}
    for idx, obj in index2object.items():
        object_groups[obj].append(idx)

    text_object_groups = {}
    unresolved_text_objects = []
    non_text_objects = []

    for obj, indices in object_groups.items():
        if not isinstance(obj, pmla.LTText):
            non_text_objects.append(obj)
            continue
        if not all([idx in index2located for idx in indices]):
            unresolved_text_objects.append(obj)
            continue
        texts = [index2located.get(idx, '') for idx in sorted(indices)]
        text_object_groups[obj] = ' '.join(texts)

    assert len(text_object_groups) + len(unresolved_text_objects) + len(non_text_objects) == len(object_groups)
    return text_object_groups, unresolved_text_objects, non_text_objects


def reorder_objects(objects, method='LRTB'):
    """Reorder objects according to their bounding boxes.

    Parameters
    ----------
    objects : list
        A list of any type of objects defined in `pdfminer.layout`.
    method : str, optional
        Method for reordering objects.
        - 'LRTB': reorder objects from top-left to bottom-right.
        - 'TBRL': reorder objects from top-right to bottom-left.

    Returns
    -------
    objects : list
        Ordered objects.

    See also: https://github.com/pdfminer/pdfminer.six/blob/7254530/pdfminer/layout.py#L573-L590
    """
    if method not in ['LRTB', 'TBRL']:
        raise ValueError(f'`method` should be one of {["LRTB", "TBRL"]}')

    laparams = pmla.LAParams()
    if method == 'LRTB':
        objects.sort(key=lambda v:(
            (1 - laparams.boxes_flow) * v.x0
            - (1 + laparams.boxes_flow) * (v.y0 + v.y1)
        ))
    else:
        objects.sort(key=lambda v:(
            - (1 + laparams.boxes_flow) * (v.x0 + v.x1)
            - (1 - laparams.boxes_flow) * v.y1
        ))
    return objects
