import json


def iter_apollo_push_payloads(html: str):
    pos = 0
    while True:
        marker = html.find(".push(", pos)
        if marker < 0:
            return
        if "ApolloSSRDataTransport" not in html[max(0, marker - 100) : marker + 100]:
            pos = marker + 6
            continue

        start = marker + 6
        depth = 0
        in_string = False
        escape = False
        end = None
        for idx in range(start, len(html)):
            char = html[idx]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
            else:
                if char == '"':
                    in_string = True
                elif char in "[{":
                    depth += 1
                elif char in "]}":
                    depth -= 1
                    if depth == 0:
                        end = idx + 1
                        break

        if end is None:
            return

        raw = html[start:end].replace(":undefined", ":null").replace("undefined", "null")
        yield json.loads(raw)
        pos = end
