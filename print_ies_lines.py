# Funcs used to help generate custom .ies profiles


def print_vangles_hangles_values(vangles, hangles, values, angle_precision=1, value_precision=2):
    assert len(vangles) * len(hangles) == len(values)

    print(f"Num vangles: {len(vangles)}")
    print(f"Num hangles: {len(hangles)}")

    def print_floats(values, precision, groupsize):
        line_count = 0
        for i, val in enumerate(values):
            line_count += 1
            print(f"{val:>6.{precision}f} ", end="")
            if (line_count % 10 == 0) or ((i + 1) % groupsize == 0):
                print()
                line_count = 0
        if line_count != 0:
            print()

    print_floats(vangles, angle_precision, len(vangles))
    print_floats(hangles, angle_precision, len(hangles))
    print_floats(values, value_precision, len(vangles))


def stripes_uniform():
    v_num = 181  # 0-180, inclusive

    vangles = []
    values = []
    for v in range(v_num):
        vangles.append(v)
        if v < 10:
            value = 0.25
        elif v >= 170:
            value = 0.75
        else:
            value = (v // 10) % 2
        values.append(value)

    print_vangles_hangles_values(vangles, [0.0], values)


def stripes_nonuniform():
    # in theory, should give identical results to stripes_uniform, but without
    # uniform spacing

    vangles = []
    values = []
    for v in range(181):
        # skip the repeating interior elements

        # bands generally start/end at 0's and 9s, modulo 10
        # exception is last row, which goes from 170 to 180 - so we skip the
        # final "9", 179
        if v == 179:
            continue
        if v % 10 not in (0, 9):
            continue

        vangles.append(v)
        if v < 10:
            value = 0.25
        elif v >= 170:
            value = 0.75
        else:
            value = (v // 10) % 2
        values.append(value)

    print_vangles_hangles_values(vangles, [0.0], values)


def vstripes_hquadrants_nonuniform():
    vangles = []
    hangles = []
    values = []

    def get_nonuniform_angles(range_end, bandsize):
        angles = []
        end_offset = bandsize - 1
        for section_start in range(0, range_end + 1, bandsize):
            angles.append(section_start)
            if section_start == range_end:
                break
            section_end = min(section_start + end_offset, range_end)
            angles.append(section_end)
        return angles

    vangles = get_nonuniform_angles(180, 10)
    # vangle bands generally start/end at 0's and 9s, modulo 10
    # exception is last row, which goes from 170 to 180 - so we skip the
    # final "9", 179
    del vangles[-2]

    hangles = get_nonuniform_angles(360, 90)

    for hangle in hangles:
        for vangle in vangles:
            if vangle < 10:
                value = 0.25
            elif vangle >= 170:
                value = 0.75
            else:
                hquadrant = (hangle // 90) % 4
                # horizontal [0, 89]: black = 0.0, vert [10, 19] is white
                # horizontal [90, 179]: black = .25, vert [10, 19] is white
                # horizontal [180, 269]: black = 0.0, vert [10, 19] is black
                # horizontal [270, 359]: black = .25, vert [10, 19] is black
                val1, val2 = {
                    0: (0.0, 1.0),
                    1: (0.25, 1.0),
                    2: (1.0, 0.0),
                    3: (1.0, 0.25),
                }[hquadrant]
                if (vangle // 10) % 2 == 0:
                    value = val1
                else:
                    value = val2
            values.append(value)
    print_vangles_hangles_values(vangles, hangles, values)
