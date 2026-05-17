import re


GRAPHQL_FIELD_ERROR_FIELDS = {"arModels", "fulfillmentOptions"}
GRAPHQL_UNUSED_AFTER_FIELD_STRIP = {
    "ButtonStatesFragment",
    "DeliveryDetailsFragment",
    "FullfillmentOptionsFragment",
    "IspuAvailabilityFragment",
    "IspuDetailsFragment",
    "IspuStoreFragment",
    "ShippingDetailsFragment",
}


def _skip_string(text, index):
    quote = text[index]
    index += 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
        elif text[index] == quote:
            return index + 1
        else:
            index += 1
    return index


def _skip_balanced(text, index, opener, closer):
    depth = 0
    while index < len(text):
        char = text[index]
        if char in {'"', "'"}:
            index = _skip_string(text, index)
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return index


def _selection_end(text, index):
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
        elif char == "(":
            index = _skip_balanced(text, index, "(", ")")
        elif char == "@":
            index += 1
            while index < len(text) and (text[index].isalnum() or text[index] == "_"):
                index += 1
            while index < len(text) and text[index].isspace():
                index += 1
            if index < len(text) and text[index] == "(":
                index = _skip_balanced(text, index, "(", ")")
        elif char == "{":
            return _skip_balanced(text, index, "{", "}")
        else:
            return None
    return None


def _remove_field_selections(query, field_names):
    if not query:
        return query
    pattern = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(sorted(map(re.escape, field_names))) + r")(?![A-Za-z0-9_])")
    output = []
    cursor = 0
    while True:
        match = pattern.search(query, cursor)
        if not match:
            output.append(query[cursor:])
            break
        end = _selection_end(query, match.end())
        if end is None:
            output.append(query[cursor : match.end()])
            cursor = match.end()
            continue
        output.append(query[cursor : match.start()])
        cursor = end
    return "".join(output)


def _remove_fragment_definitions(query, fragment_names):
    if not query:
        return query
    for fragment_name in fragment_names:
        pattern = re.compile(r"\bfragment\s+" + re.escape(fragment_name) + r"\s+on\s+[A-Za-z0-9_]+\s*{")
        while True:
            match = pattern.search(query)
            if not match:
                break
            end = _skip_balanced(query, query.rfind("{", match.start(), match.end()), "{", "}")
            query = query[: match.start()] + query[end:]
    return query


def sanitize_product_list_query(query):
    query = _remove_field_selections(query, GRAPHQL_FIELD_ERROR_FIELDS)
    query = _remove_fragment_definitions(query, GRAPHQL_UNUSED_AFTER_FIELD_STRIP)
    return query
