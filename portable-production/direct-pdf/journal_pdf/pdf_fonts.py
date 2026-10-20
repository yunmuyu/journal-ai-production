def normalize_type0_font_names(doc, postscript_names=None):
    postscript_names=postscript_names or {}
    seen=set()
    for page in doc:
        for row in page.get_fonts(full=True):
            xref=row[0]
            if xref in seen or row[2]!='Type0':continue
            seen.add(xref)
            kind,value=doc.xref_get_key(xref,'DescendantFonts')
            if kind!='array':continue
            refs=[int(token) for token in value.replace('[',' ').replace(']',' ').split() if token.isdigit()]
            if not refs:continue
            descendant=refs[0]
            name_kind,ps_name=doc.xref_get_key(descendant,'BaseFont')
            if name_kind!='name' or not ps_name.startswith('/') or ps_name=='/(null)':
                role=row[4].removeprefix('JFW_')
                ps_name='/'+postscript_names.get(role,'')
            if ps_name=='/':continue
            doc.xref_set_key(xref,'BaseFont',ps_name)
            doc.xref_set_key(descendant,'BaseFont',ps_name)
            descriptor_kind,descriptor_value=doc.xref_get_key(descendant,'FontDescriptor')
            if descriptor_kind=='xref':
                descriptor=int(descriptor_value.split()[0])
                doc.xref_set_key(descriptor,'FontName',ps_name)


def finalize_font_descriptors(doc):
    """Complete proven descriptor metrics before saving a generated PDF."""
    from .font_descriptors import complete_descriptors
    complete_descriptors(doc)
