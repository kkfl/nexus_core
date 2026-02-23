def main():
    import glob

    files = glob.glob("migrations/versions/*_carrier*.py")
    if not files:
        return
    file = sorted(files)[-1]

    with open(file) as f:
        lines = f.readlines()

    out = []

    for line in lines:
        if "op.drop_table" in line and (
            "automation" in line or "registry" in line or "dns" in line
        ):
            continue
        if "op.drop_index" in line and (
            "automation" in line or "registry" in line or "dns" in line
        ):
            continue
        if "op.alter_column" in line and (
            "automation" in line or "registry" in line or "dns" in line
        ):
            continue

        out.append(line)

    with open(file, "w") as f:
        f.writelines(out)


if __name__ == "__main__":
    main()
