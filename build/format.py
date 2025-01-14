import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import timeit
import traceback


def read_file(filename):
    with open(filename, "rb") as fh:
        return fh.read().decode("utf-8")


def write_file(filename, data):
    fd = tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=os.path.basename(filename),
        dir=os.path.dirname(filename),
        delete=False,
    )
    try:
        fd.write(data.encode("utf-8"))
    finally:
        fd.close()
    while True:
        try:
            shutil.move(fd.name, filename)
            return
        except BaseException:
            time.sleep(0.1)


def compile_fields(fields):
    reply = []
    for p, a, sep, b in fields:
        cmt = r"\/\/ *.+"
        full = r"\n((?:" + a + sep + b + "(?: +" + cmt + r")?\n)+)"
        line = r"(" + a + sep + ")(" + b + ") *( " + cmt + r")?\n"
        re_full = re.compile(full)
        re_line = re.compile(line)
        reply.append((re_full, re_line, p))
    return reply


def align_fields(data, re_blobs, re_lines, align):
    for blob in re_blobs.findall(data):
        if blob.count("\n") < 2:
            continue
        # print(blob)
        pad_a = 0
        pad_b = 0
        lines = re_lines.findall(blob)
        num_c = 0
        for a, b, c in lines:
            pad_a = max(pad_a, len(a))
            if len(c) > 0:
                pad_b = max(pad_b, len(b))
                num_c += 1
        if num_c < 2:
            pad_b = 0
        if align:
            pad_a = (pad_a + align - 1) & -align
        dst = ""
        for a, b, c in lines:
            dst += a.ljust(pad_a) + b.ljust(pad_b) + c + "\n"
        data = data.replace(blob, dst)
    return data


def apply_patterns(data, patterns):
    for p, r in patterns:
        dst = ""
        while dst != data:
            dst = p.sub(r, data)
            data, dst = dst, data
    return data


def process(data, pre_patterns, re_fields, post_patterns):
    if not len(data):
        return data
    if data[-1] != "\n":
        data += "\n"
    data = apply_patterns(data, pre_patterns)
    for blobs, lines, align in re_fields:
        data = align_fields(data, blobs, lines, align)
    data = apply_patterns(data, post_patterns)
    return data


def main():
    pre_patterns = [
        # break line after lambda
        (r"(\n *)(.+\[[^]]*\](?: *\([^)]*\))?(?: -> .+)?) {\n", r"\1\2\1{\n"),
    ]
    fields = [
        # align case ...: return ...;
        (4, r" +(?:case .+|default):", " +", r"[^ ].+;"),
        # align method names
        (
            4,
            r" *\b[^\n=]*?[^\n=, +]",
            " +",
            r"(?:\b\w+|\(\*\w+\)) *\([^\n={}]*\)(?: *const)?(?: override| += 0)?;",
        ),
        # align method parameters
        (
            4,
            r" *\b[^\n=]*?[^\n=, ] +(?:\b\w+|\(\*\w+\))",
            " *",
            r"\([^\n={}]*\)(?: *const)?(?: override| += 0)?;",
        ),
    ]
    post_patterns = [
        # put forward declarations on one line
        (r"\n(namespace \w+)\n{\n +((?:\w+) \w+;)\n}\n", r"\n\1 { \2 }\n"),
        # remove empty namespaces close comments
        (r"(\n *}) // namespace\n", r"\1\n"),
        # align back ...] =\n{\n
        (r"(\n *)(.+?)\] =\n +{", r"\1\2] =\1{"),
        # remove whitespaces after return
        (r"return +", r"return "),
        # enforce space after comment
        (r" //([^ ])", r" // \1"),
        # remove trailing whitespace
        (r"[ \t\r]+\n", r"\n"),
        # remove = 0 misalignment
        (r"\) += 0;", r") = 0;"),
    ]
    for i, (p, t) in enumerate(pre_patterns):
        pre_patterns[i] = re.compile(p), t
    for i, (p, t) in enumerate(post_patterns):
        post_patterns[i] = re.compile(p), t
    re_fields = compile_fields(fields)

    total = 0

    def round_time(arg):
        return int(round(arg * 1000))

    # store last modified times
    files = sys.argv[3:]
    targets = []
    for filename in files:
        data = read_file(filename)
        targets.append((filename, data))

    clang = os.path.abspath(sys.argv[2])
    for filename, data in targets:
        t = timeit.default_timer()
        after_clang = subprocess.check_output([clang, "-style=file", filename]).decode()
        value = process(after_clang, pre_patterns, re_fields, post_patterns)
        step = timeit.default_timer() - t
        # print("%4dms: %s" % (round_time(step), f))
        total += step
        if value != data:
            write_file(filename, value)
            print("fmt: %s" % os.path.basename(filename))
    # print("fmt: %s %d files %dms" % (target, len(files), round_time(total)))
    with open(sys.argv[1], "wb") as fh:
        fh.write(b"")

    return 0


def check_version(min_ver):
    try:
        clang = os.path.abspath(sys.argv[2])
        args = [clang, "--version"]
        out = subprocess.check_output(args).decode()
        print(out)
        m = re.search(r"clang-format version (\d+)\.\d+\.\d+\b", out)
        version = int(m.group(1))
        if version >= min_ver:
            return 0

        print(f"invalid clang-format version: {version} < {min_ver}")
    except:
        traceback.print_exc()
    return -1


if __name__ == "__main__":
    if sys.argv[1] == "--version":
        ret = check_version(12)
    else:
        ret = main()
    sys.exit(ret)
