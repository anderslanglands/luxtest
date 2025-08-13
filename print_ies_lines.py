# Funcs used to help generate custom .ies profiles


def print_vangles_hangles_values(vangles, hangles, values, angle_precision=1, value_precision=2, vals_per_line=10):
    assert len(vangles) * len(hangles) == len(values)

    print(f"Num vangles: {len(vangles)}")
    print(f"Num hangles: {len(hangles)}")

    def print_floats(values, precision, groupsize):
        line_count = 0
        for i, val in enumerate(values):
            line_count += 1
            print(f"{val:>6.{precision}f} ", end="")
            if (line_count % vals_per_line == 0) or ((i + 1) % groupsize == 0):
                print()
                line_count = 0
        if line_count != 0:
            print()

    print_floats(vangles, angle_precision, len(vangles))
    print_floats(hangles, angle_precision, len(hangles))
    print_floats(values, value_precision, len(vangles))


# Used to make `test_vstripes_uniform.ies`
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


# Used to make `test_vstripes_nonuniform.ies`
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


# Used to make `test_vstripes_hquadrants_nonuniform.ies`
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


# Used to make `test_vstripes_hquadrants_nonuniform_aimDown.ies`:
#     vstripes_hquadrants_nonuniform_bounded(0, 50, 5, .1)
# Used to make `test_vstripes_hquadrants_nonuniform_aimUp.ies`:
#     vstripes_hquadrants_nonuniform_bounded(130, 180, 5, .1)


# Note - innermost and outermost bands always forced to black, so we set range to 50 degrees, so first "real"
# (non-black) band is at 45
def vstripes_hquadrants_nonuniform_bounded(v_start: float, v_end: float, v_band_size: float, v_transition_size: float):
    vangles = []
    hangles = []
    values = []

    if v_end <= v_start:
        raise ValueError(f"v_end ({v_end}) must be > v_start ({v_start})")
    if v_transition_size >= v_band_size:
        raise ValueError(f"v_transition_size ({v_transition_size}) must be < v_band_size ({v_band_size})")

    max_vband_size = (v_end - v_start) / 4.0
    if v_band_size > max_vband_size:
        # first and last bands are always forced to be black...
        # So we want at least 2 inner bands to ensure we can see some stripes,
        # so we need minimum 4 bands
        raise ValueError(f"Band size ({v_band_size}) must be < {max_vband_size} to ensure we have at least 4 bands")

    def get_nonuniform_angles(range_start, range_end, band_size, transition_size):
        assert band_size >= 0
        angles = []
        end_offset = band_size - transition_size
        band_start = range_start

        # The final angle value must always be the range_end
        # ...so if our last band_start == range_end, the the last band
        # would be a pair of angles both at range_end... so our continue
        # condition is < range_end, not <= range_end
        while band_start < range_end:
            angles.append(band_start)
            angles.append(band_start + end_offset)
            band_start += band_size
        # force last angle to always be range end
        angles[-1] = range_end
        return angles

    vangles = get_nonuniform_angles(v_start, v_end, v_band_size, v_transition_size)

    # we should have guaranteed this by our `v_band_size > max_vband_size` check
    assert len(vangles) >= 8
    assert len(vangles) % 2 == 0

    hangles = get_nonuniform_angles(0, 360, 90, 1)
    # hangles repeat - so 0 == 360. We need to insert an extra angle to ensure
    # we have 9 hangles - (4 bands) x (2 values per band) + (1 repeated 360)
    hangles.insert(-1, 359)

    for hangle in hangles:
        # first band is always
        for vi in range(len(vangles)):
            # The point of this light is to display it contained to a certain
            # vertical range, so as we make it broader or shrink with
            # angleScale, we can see it's limits - so we always force
            # first and last vertical bands to be black
            if vi <= 1 or vi >= len(vangles) - 2:
                values.append(0.0)
                continue
            if hangle < 90 or hangle == 360:
                hquadrant = 0
            elif hangle < 180:
                hquadrant = 1
            elif hangle < 270:
                hquadrant = 2
            else:
                hquadrant = 3

            # we force first band to be black - so the first band that varies
            # is the 2nd band

            # horizontal [0, 89]: black = 0.0, 2nd band is white
            # horizontal [90, 179]: black = .25, 2nd band is white
            # horizontal [180, 269]: black = 0.0, 2nd band is black
            # horizontal [270, 359]: black = .25, 2nd band is black
            val1, val2 = {
                0: (0.0, 1.0),
                1: (0.25, 1.0),
                2: (1.0, 0.0),
                3: (1.0, 0.25),
            }[hquadrant]

            # vangles just flip every 2
            if vi % 4 <= 1:
                value = val1
            else:
                value = val2
            values.append(value)

    vals_per_line = 10
    if len(vangles) % vals_per_line == 0:
        # in this case, every line in the list of vangles would have the same
        # number of values, making it hard to visually distinguish where each
        # group starts and ends when reading the file - so bump it up
        vals_per_line += 1
    print_vangles_hangles_values(vangles, hangles, values, vals_per_line=vals_per_line)
