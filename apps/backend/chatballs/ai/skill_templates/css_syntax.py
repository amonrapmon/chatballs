"""Reject truncated CSS that tinycss2 would recover at end of input."""


def balanced(value):
    stack = []
    quote = None
    comment = False
    index = 0
    while index < len(value):
        char = value[index]
        pair = value[index:index + 2]
        if comment:
            if pair == "*/":
                comment = False
                index += 1
        elif quote:
            if char == "\\":
                index += 1
            elif char == quote:
                quote = None
        elif pair == "/*":
            comment = True
            index += 1
        elif char == "\\":
            index += 1
        elif char in {"'", '"'}:
            quote = char
        elif char in "{([":
            stack.append(char)
        elif char in "})]":
            if not stack or stack.pop() != {"}": "{", ")": "(", "]": "["}[char]:
                return False
        index += 1
    return not stack and quote is None and not comment
