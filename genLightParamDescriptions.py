#!/usr/bin/env python

"""Generate .json file describing the various parameters for each light"""

import argparse
import collections.abc
import dataclasses
import inspect
import json
import math
import os
import sys
import traceback

from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Tuple, TypeAlias, Union

THIS_FILE = os.path.abspath(inspect.getsourcefile(lambda: None) or __file__)
THIS_DIR = os.path.dirname(THIS_FILE)

if THIS_DIR not in sys.path:
    sys.path.append(THIS_DIR)

try:
    from pxr import Sdf, Usd, UsdLux
except ImportError:
    import pip_import

    pip_import.pip_import("pxr", "usd-core")
    from pxr import Sdf, Usd, UsdLux

import luxtest_const

IntFloat: TypeAlias = Union[int, float]


###############################################################################
# Constants
###############################################################################

USD_DIR = os.path.join(THIS_DIR, "usd")

LIGHT_NAME_SUFFIX = "_light"
OUTPUT_JSON_PATH = os.path.join(THIS_DIR, "light_descriptions.json")
USD_EXTENSIONS = (".usd", ".usda", ".usdc")

MISSING = object()

AREA_LIGHT_SUMMARY_OVERRIDES = {
    (1, 5): "light rotate worldZ from 0 to 60",
    (26, 30): "light rotate under shear + nonuniform scale",
    (46, 50): "focusTint from black to green to white",
}

SUMMARY_OVERRIDES = {
    "distant": {
        (1, 5): "light rotate worldZ from 0 to 80",
        (6, 10): "cam rotate from 0 to 80",
    },
    "iesTest": {
        (1, 1): "ies:angleScale=0 ref",
        (11, 11): "ies:angleScale=0 ref",
        (21, 21): "ies:angleScale=0 ref",
        (31, 31): "ies:angleScale=0 ref",
        (41, 41): "no ies:file ref",
    },
}

for area_light in ("sphere", "disk", "cylinder", "rect"):
    SUMMARY_OVERRIDES[area_light] = dict(AREA_LIGHT_SUMMARY_OVERRIDES)
del area_light

COLOR_NAMES = {
    (0.0, 0.0, 0.0): "black",
    (1.0, 1.0, 1.0): "white",
    (1.0, 0.0, 0.0): "red",
    (0.0, 1.0, 0.0): "green",
    (0.0, 0.0, 1.0): "blue",
}

###############################################################################
# Utilities
###############################################################################


def is_ipython():
    try:
        __IPYTHON__  # type: ignore
    except NameError:
        return False
    return True


def is_iterable(obj) -> bool:
    try:
        iter(obj)
    except Exception:
        return False
    return True


def is_sorted(vals: Iterable):
    last = MISSING
    for current in vals:
        if last is MISSING:
            last = current
        elif last > current:
            return False
    return True


def _standardize_val_for_comparison(val):
    if type(val).__name__.startswith("Matrix"):
        flat = []
        for vec in val:
            flat.extend(list(vec))
        return flat
    elif type(val).__name__.startswith("Vec"):
        return list(val)
    if isinstance(val, (str, bytes)):
        return val
    try:
        iter(val)
    except Exception:
        return val
    # standardize all iterables as lists
    return list(val)


def vals_close(val1, val2):
    val1 = _standardize_val_for_comparison(val1)
    val2 = _standardize_val_for_comparison(val2)
    if isinstance(val1, float) or isinstance(val2, float):
        return math.isclose(val1, val2)
    elif type(val1) != type(val2):
        return False
    elif isinstance(val1, list):
        if len(val1) != len(val2):
            return False
        return all(vals_close(v1, v2) for v1, v2 in zip(val1, val2))
    elif isinstance(val1, dict):
        if set(val1) != set(val2):
            return False
        for key, v1 in val1.items():
            v2 = val2[key]
            if not vals_close(v1, v2):
                return False
        return True
    return val1 == val2


def to_int_float(num):
    if isinstance(num, (int, float)):
        return num
    if not isinstance(num, str):
        raise TypeError(f"to_int_float only accepts int/float/str - got: {num}")
    try:
        return int(num)
    except ValueError:
        return float(num)


def to_json_val(obj):
    if isinstance(obj, (int, float, str, type(None))):
        return obj
    elif isinstance(obj, Sdf.AssetPath):
        return obj.path
    elif isinstance(obj, collections.abc.Mapping):
        return {to_json_val(key): to_json_val(val) for key, val in obj.items()}
    elif is_iterable(obj):
        return list(to_json_val(x) for x in obj)
    raise RuntimeError(f"Do not know how to serialize: {obj}")


def format_val(val):
    if isinstance(val, float):
        if math.isclose(val, int(val)):
            val = int(val)
        else:
            return f"{val:.1f}".lstrip("0")
    elif isinstance(val, str):
        split = val.split("/")
        while split and split[0] in (".", ".."):
            del split[0]
        val = "/".join(split)
        return repr(val)
    elif isinstance(val, bool):
        # on/off are shorter than True/False
        return "on" if val else "off"
    elif isinstance(val, (list, tuple)) and len(val) == 3:
        # we assume color for now
        val = tuple(val)
        for color3, name in COLOR_NAMES.items():
            if all(math.isclose(a, b, rel_tol=1e-7) for (a, b) in zip(color3, val)):
                return name
    return str(val)


def format_attr(attr_name):
    split = attr_name.split(":")
    if split[0] == "inputs":
        del split[0]
    if split[0] == "shaping":
        del split[0]
    return ":".join(split)


def get_light_name(light):
    if isinstance(light, Usd.Prim):
        light = light.GetName()
    if not light.endswith(LIGHT_NAME_SUFFIX):
        raise ValueError(f"light did not end with {LIGHT_NAME_SUFFIX!r}: {light}")
    return light[: -len(LIGHT_NAME_SUFFIX)]


def get_fallback(attr: Usd.Attribute):
    override = luxtest_const.DEFAULT_OVERRIDES.get(attr.GetName())
    if override is not None:
        return override
    if not attr.HasFallbackValue():
        # xformOp:transform technically has no fallback, but we assume identity
        sdf_type = attr.GetTypeName().type
        py_type = sdf_type.pythonClass
        if py_type and py_type.__module__ == "pxr.Gf":
            return py_type()
        elif sdf_type.typeName == "SdfAssetPath":
            return ""
        return None
    prim_def = attr.GetPrim().GetPrimDefinition()
    attr_def = prim_def.GetAttributeDefinition(attr.GetName())
    if not attr_def:
        raise RuntimeError(f"Error getting attr defintion for {attr.GetPath()}")
    return attr_def.GetFallbackValue()


def find_usds(path: str, recurse=False):
    if os.path.isfile(path):
        paths = [path]
    elif os.path.isdir(path):
        paths = []
        for entry in os.scandir(path):
            if entry.is_file() and entry.name.endswith(USD_EXTENSIONS):
                paths.append(entry.path)
            elif entry.is_dir() and recurse:
                paths.extend(find_usds(entry.path), recurse=recurse)
    else:
        raise ValueError(f"path was not a file or directory: {path}")
    return paths


def get_override_group(light_name, frame):
    for start_end in SUMMARY_OVERRIDES.get(light_name, {}).keys():
        if frame >= start_end[0] and frame <= start_end[1]:
            return start_end
    return None


###############################################################################
# Dataclasses
###############################################################################


class FrameRange(NamedTuple):
    start: int
    end: int

    @property
    def num_frames(self):
        return self.end - self.start + 1

    def __str__(self):
        return f"{self.start}:{self.end}"

    @classmethod
    def from_str(cls, frames_str) -> "FrameRange":
        if ":" in frames_str:
            split = frames_str.split(":")
            if len(split) > 2:
                raise ValueError(
                    f"frames may only have a single ':', to denote start:end (inclusive) - got: {args.frames}"
                )
            frames = tuple(int(x) for x in split)
        else:
            frame = int(frames_str)
            frames = (frame, frame)
        return cls(*frames)


@dataclasses.dataclass
class FrameGroup:
    """A frame group is a range over which exactly 1 parameter is varying, and in the same direction"""

    frames: FrameRange
    varying: Dict[str, Dict[IntFloat, Any]]  # dictionary from attr names to it's per-frame values
    non_default_constants: Dict[str, Any]  # attributes that were constant, but not at their default value

    @classmethod
    def from_dict(cls, data):
        # if coming from json, all keys were stringified...
        data = dict(data)
        for attrname, framevals in data["varying"].items():
            framevals = {to_int_float(frame): val for frame, val in framevals.items()}
            data["varying"][attrname] = framevals
        data["frames"] = FrameRange(*data["frames"])
        return cls(**data)


@dataclasses.dataclass
class FrameGroupTracker:
    """Data associated with a Frame group, used by FrameGroupFinder"""

    light_name: str
    # for each frame, dict from attr names to values
    # frames and attrs are both sorted
    frame_vals: Dict[IntFloat, Dict[str, Any]]

    # varying attributes - generally only 1 (because we only auto-group if exactly 1 varying)
    # maps from attr name to whether it is increasing
    varying: Dict[str, bool]
    constants: List[str]  # constant, but not at default
    defaults: List[str]  # constant, AND default

    override_group: Optional[FrameRange] = dataclasses.field(init=False, default=None)

    def __post_init__(self):
        # sort the things...
        self.constants = sorted(self.constants)
        self.defaults = sorted(self.defaults)

        attrs = self.attrs()

        sorted_frame_vals = {}
        for frame in sorted(self.frame_vals):
            vals = self.frame_vals[frame]
            try:
                sorted_frame_vals[frame] = {attr: vals[attr] for attr in attrs}
            except KeyError as err:
                print(f"Frame {frame} was missing attr {err.args[0]!r}")
                raise
        self.frame_vals = sorted_frame_vals

        # just get override group of first frame - we should only create a
        # FrameGroupTracker for frames in the same override group - validate() will
        # confirm
        self.override_group = get_override_group(self.light_name, list(self.frame_vals)[0])

        # verify assumptions
        self.validate()

    def frames(self):
        return tuple(self.frame_vals)

    def attrs(self) -> Tuple[str]:
        attrs = list(self.constants)
        attrs.extend(self.defaults)
        if self.varying:
            attrs.extend(self.varying)
        return tuple(sorted(attrs))

    def validate(self):
        for frame in self.frame_vals:
            override_group = get_override_group(self.light_name, frame)
            if override_group != self.override_group:
                raise RuntimeError(
                    "Tried to create a FrameGroupTracker with frames from different override groups -"
                    f" {self.override_group} and {override_group}"
                )

        attrs = self.attrs()
        if len(attrs) != len(set(attrs)):
            dupe = None
            known = set()
            for a in attrs:
                if a in known:
                    dupe = a
                    break
                known.add(a)
            raise ValueError(
                f"duplicate attribute: {dupe} - varying: {sorted(self.varying)} - constants: {self.constants} -"
                f" defaults: {self.defaults}"
            )

        if len(self.frame_vals) == 0:
            raise ValueError("empty frames")
        if len(self.frame_vals) == 1:
            if self.varying:
                raise ValueError("had only 1 frame, but had varying attrs")

        if not is_sorted(self.frame_vals):
            raise ValueError("attrs were not sorted")

        for frame, vals in self.frame_vals.items():
            if tuple(vals) != attrs:
                # Something is wrong with attrs on this frame - figure out what,
                # and print more informative error
                vals_set = set(vals)
                attrs_set = set(attrs)
                if vals_set != attrs_set:
                    missing = attrs_set - vals_set
                    if missing:
                        raise ValueError(f"frame {frame} missing attributes: {', '.join(missing)}")
                    extra = vals_set - attrs_set
                    raise ValueError(f"frame {frame} had extra attributes: {', '.join(extra)}")
                # same set, so must just be out of order
                if not is_sorted(vals):
                    raise ValueError(f"attrs for frame {frame} not sorted: {', '.join(vals)}")
                elif not is_sorted(attrs):
                    raise ValueError(f"self.attrs() was not sorted: {', '.join(attrs)}")
                # hmm... not sure what's wrong?
                raise ValueError(f"Unknown error with attributes for frame {frame} - wanted {attrs}, got {tuple(vals)}")

    def find_varying_vals(
        self, this_frame: IntFloat, other: "FrameGroupTracker", other_frame: IntFloat
    ) -> Dict[str, bool]:
        """Finds all attributes that differ between this and other FrameGroupTracker

        returns mapping from attr name to whether it increased (ie, if False, it decreased)
        """
        this_vals = self.frame_vals[this_frame]
        other_vals = other.frame_vals[other_frame]
        # returns dict from attr name to "increasing" bool
        attr_to_increasing = {}
        for attr in self.attrs():
            old = this_vals[attr]
            new = other_vals[attr]
            if not vals_close(old, new):
                attr_to_increasing[attr] = new > old
        return attr_to_increasing

    def combine(self, other: "FrameGroupTracker") -> bool:
        """Adds the frame_vals from single-frame FrameGroupTracker other to this group, if possible

        Returns true if the the frame_vals were combined (in which case other can be discarded)
        """
        attrs = self.attrs()
        if attrs != other.attrs():
            raise ValueError("to combine two FrameGroups, must be over same set of attrs")

        # below two are just confirming assumptions, so I don't have to think about general case...
        if len(other.frame_vals) != 1:
            raise ValueError("currenly only support adding a frame group of size 1")
        if max(self.frame_vals) >= min(other.frame_vals):
            raise ValueError("currenly only support adding a frame group whose frames are all strictly greater")
        can_combine = False
        this_frame = self.frames()[-1]
        other_frame = other.frames()[0]

        new_varying = self.find_varying_vals(this_frame, other, other_frame)

        if self.override_group is not None or other.override_group is not None:
            # at least one is an an override group - we can definitely say whether they should be grouped based on that
            can_combine = self.override_group == other.override_group
        elif not self.varying:
            if len(new_varying) == 1:
                can_combine = True
        elif len(new_varying) == 1 and new_varying == self.varying:
            can_combine = True

        if can_combine:
            for attr, increasing in new_varying.items():
                if attr in self.varying:
                    continue
                self.varying[attr] = increasing

                # remove varying attr from defaults or constants
                try:
                    self.constants.remove(attr)
                except ValueError:
                    try:
                        self.defaults.remove(attr)
                    except ValueError:
                        raise RuntimeError(
                            f"programming logic error - new varying value {attr} not found in either "
                            f"constants ({self.constants}) or defaults ({self.defaults})"
                        )

            # only thing left to do is add in the new frame_vals
            self.frame_vals.update(other.frame_vals)
            self.validate()
        return can_combine

    @classmethod
    def for_frame(
        cls,
        light_name: str,
        frame: IntFloat,
        vals: Dict[Usd.Attribute, IntFloat],
        default_vals: Optional[Dict[str, Any]] = None,
    ) -> "FrameGroupTracker":
        # if we only have one frame, there's nothing to vary, so all we can do
        # is check which are at defaults
        if default_vals is None:
            default_vals = {}

        default_attrs = []
        constant_attrs = []

        for attr, val in vals.items():
            name = attr.GetName()
            default = default_vals.get(name, MISSING)
            if default is MISSING:
                default = get_fallback(attr)
                default_vals[name] = default
            if vals_close(val, default):
                default_attrs.append(name)
            else:
                constant_attrs.append(name)
        vals_by_name = {attr.GetName(): val for attr, val in vals.items()}
        frame_vals = {frame: vals_by_name}
        return cls(
            light_name=light_name,
            frame_vals=frame_vals,
            varying={},
            constants=constant_attrs,
            defaults=default_attrs,
        )

    @classmethod
    def for_frame_attrs(
        cls,
        light_name: str,
        frame: IntFloat,
        attrs: Iterable[Usd.Attribute],
        default_vals: Optional[Dict[str, Any]] = None,
    ) -> "FrameGroupTracker":
        all_names = sorted(attr.GetName() for attr in attrs)
        if len(all_names) != len(set(all_names)):
            raise ValueError(f"name clash in attrs: {attrs}")
        vals = {attr: to_json_val(attr.Get(frame)) for attr in attrs}
        default_vals = {}
        return cls.for_frame(light_name, frame, vals, default_vals=default_vals)

    def to_frame_group(self) -> FrameGroup:
        frames = self.frames()
        start = frames[0]
        end = frames[-1]
        if self.varying:
            varying_vals = {}
            for attr in self.varying:
                varying_vals[attr] = {frame: vals[attr] for frame, vals in self.frame_vals.items()}
        else:
            varying_vals = {}

        if self.constants:
            # constant vals by def should be same for all frames - grab first
            first_vals = next(iter(self.frame_vals.values()))
            constants = {n: first_vals[n] for n in self.constants}
        else:
            constants = {}

        # xformOps are commonly set to non-default, and uninteresting for us - only
        # include them if they're varying
        for key in list(constants):
            if key.startswith("xformOp:"):
                del constants[key]

        return FrameGroup(
            frames=(start, end),
            varying=varying_vals,
            non_default_constants=constants,
        )


# Note: this assumes defaults can't be animated, which isn't strictly always
# true in Houdini, but should be for our scene...


@dataclasses.dataclass
class FrameGroupFinder:
    light_name: str
    all_attrs: List[Usd.Attribute]
    all_frames: List[IntFloat]
    frame_groups: List[FrameGroupTracker] = dataclasses.field(default_factory=list)

    def run(self):
        for frame in self.all_frames:
            self.run_frame(frame)

    def run_frame(self, frame: IntFloat):
        new_group = FrameGroupTracker.for_frame_attrs(self.light_name, frame, self.all_attrs)
        if not self.frame_groups:
            # special case, very first frame
            self.frame_groups.append(new_group)
            return
        last_group = self.frame_groups[-1]
        combined = last_group.combine(new_group)
        if not combined:
            self.frame_groups.append(new_group)

    @classmethod
    def find(
        cls, light_name: str, all_attrs: Iterable[Usd.Attribute], all_frames: Iterable[IntFloat]
    ) -> List[FrameGroup]:
        finder = cls(light_name=light_name, all_attrs=list(all_attrs), all_frames=list(all_frames))
        finder.run()
        return [x.to_frame_group() for x in finder.frame_groups]


@dataclasses.dataclass
class LightParamDescription:
    usd_path: str
    frame_groups: List[FrameGroup]
    frames: FrameRange  # start/end
    attrs: List[str]

    @classmethod
    def empty(cls):
        return cls("", [], (1, 1), [])

    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        data["frame_groups"] = [FrameGroup.from_dict(x) for x in data["frame_groups"]]
        data["frames"] = FrameRange(*data["frames"])
        return cls(**data)

    @classmethod
    def from_light_prim(cls, light: Usd.Prim) -> Dict[str, any]:
        usd_path = light.GetStage().GetRootLayer().realPath

        light_name = get_light_name(light)

        attrs = light.GetAuthoredAttributes()
        attrs = [x for x in attrs if not x.GetNamespace().split(":", 1)[0] == "houdini"]
        attrs = [x for x in attrs if x.GetName() != "extent"]
        # ValueMightBeTimeVarying doesn't GUARANTEE that results will have
        # more than 1 time sample - so just use slower GetTimeSamples()
        attrs = [x for x in attrs if len(x.GetTimeSamples()) > 1]
        attrs.sort(key=lambda x: x.GetPath())

        all_samples = Usd.Attribute.GetUnionedTimeSamples(attrs)

        start = math.inf
        end = -math.inf

        if all_samples:
            all_samples.sort()
            # we render at fixed frames, no at samples - so get first / last, then iterate over range
            start = math.floor(all_samples[0])
            end = int(all_samples[-1])
        light_overrides = SUMMARY_OVERRIDES.get(light_name, {})
        for override_start, override_end in light_overrides:
            start = min(start, override_start)
            end = max(end, override_end)
        if start == math.inf:
            start = end = 1

        if not all_samples:
            # constant
            return cls(usd_path=usd_path, frame_groups=[], frames=(start, end), attrs=[])

        frames_list = list(range(start, end + 1))
        frame_groups = FrameGroupFinder.find(light_name, all_attrs=attrs, all_frames=frames_list)
        attr_names = [x.GetName() for x in attrs]

        # xformOps are commonly set to non-default, and uninteresting for us - only
        # include them if they're varying
        all_varying = set()
        for group in frame_groups:
            all_varying.update(group.varying)
        attr_names = [x for x in attr_names if not x.startswith("xformOp:") or x in all_varying]

        return cls(usd_path=usd_path, frame_groups=frame_groups, frames=(start, end), attrs=attr_names)


class DataclassJsonEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        # Let the base class default method raise the TypeError
        return super().default(o)


###############################################################################
# Core functions
###############################################################################


def write_light_param_descriptions(path: str, recurse: bool = False, json_out_path=OUTPUT_JSON_PATH, errors="raise"):
    usd_paths = find_usds(path, recurse=recurse)
    if not usd_paths:
        raise ValueError(f"Could not find any USD files at path: {path}")
    descriptions = {}
    for usd_path in usd_paths:
        stage = Usd.Stage.Open(usd_path)
        print(f"Processing: {usd_path}")
        descriptions.update(gen_light_param_descriptions(stage, errors=errors))

    print(f"Got {len(descriptions)} descriptions")
    print("=" * 80)
    for light_name, desc in descriptions.items():
        print()
        print(f"{light_name}:")
        print(summarize_light(light_name, desc))
    print("=" * 80)
    print(f"Writing as json: {json_out_path}")
    with open(json_out_path, "w", encoding="utf8") as writer:
        json.dump(descriptions, writer, sort_keys=True, indent=4, cls=DataclassJsonEncoder)
    return


def find_summary_override(light_name: str, start: int, end: int):
    light_overrides = SUMMARY_OVERRIDES.get(light_name)
    if light_overrides is None:
        return None
    for frames, desc in light_overrides.items():
        override_start, override_end = frames
        if override_start <= start and end <= override_end:
            return frames, desc
    return None


def get_light_group_summaries(light_name, light_description):
    if not light_description.frame_groups:
        return []

    summaries_by_start_frame = {}
    for group in light_description.frame_groups:
        start, end = group.frames

        frame_desc = ""
        override_desc = ""
        varying_desc = ""
        override = find_summary_override(light_name, start, end)
        if override is not None:
            override_frames, override_desc = override
            start, end = override_frames
            varying_desc = override_desc
        elif not group.varying:
            frame_desc = "(constant)"
        if not frame_desc:
            if not varying_desc:
                varying_descs = []
                for varying_attr, vals in group.varying.items():
                    varying_descs.append(
                        f"{format_attr(varying_attr)} from {format_val(vals[start])} to {format_val(vals[end])}"
                    )
                varying_desc = ", ".join(varying_descs)

            constants = group.non_default_constants
            if not constants:
                constants_desc = ""
            else:
                constant_descs = []
                for const_name, val in constants.items():
                    constant_descs.append(f"{format_attr(const_name)}={format_val(val)}")
                constants_desc = ", ".join(constant_descs)
                constants_desc = f" ({constants_desc})"
            frame_desc = f"{varying_desc}{constants_desc}"

        if start == end:
            frame_str = str(start)
        else:
            frame_str = f"{start}-{end}"

        summaries_by_start_frame[start] = f"{frame_str}: {frame_desc}"
    return summaries_by_start_frame


def summarize_light(light_name, light_description):
    summaries = get_light_group_summaries(light_name, light_description)
    if not summaries:
        return ""

    return "\n".join(summaries.values())


def gen_light_param_descriptions(stage: Usd.Stage, errors="raise"):
    lights = [x for x in stage.Traverse() if x.HasAPI(UsdLux.LightAPI)]
    if not lights:
        raise RuntimeError(f"stage had no lights: {stage}")

    all_descs = {}
    layer = stage.GetRootLayer()
    stage_path = layer.realPath
    if not stage_path:
        stage_path = layer.identifier
    for light in lights:
        try:
            light_name = get_light_name(light)
            light_desc = LightParamDescription.from_light_prim(light)
            if light_name in all_descs:
                raise ValueError(f"Light name appeared twice: {light_name}")
            all_descs[light_name] = light_desc
        except Exception:
            print(f"WARNING: Error processing light {light.GetPath()} in stage {stage_path}")
            if errors == "raise":
                raise

    return all_descs


def read_descriptions(path=OUTPUT_JSON_PATH):
    with open(path, "r", encoding="utf8") as reader:
        raw_data = json.load(reader)
    # convert back to LightParamDescription objects
    return {name: LightParamDescription.from_dict(data) for name, data in raw_data.items()}


###############################################################################
# CLI
###############################################################################


def get_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=USD_DIR,
        help="path to a single usd file or a directory to search for usd files",
    )
    parser.add_argument(
        "-r",
        "--recurse",
        action="store_true",
        help="if PATH is a directory, whether to search sub-directories recursively",
    )
    parser.add_argument(
        "-e",
        "--errors",
        choices=("raise", "warn"),
        default="raise",
        help=(
            "How to handle errors when processing a given usda or light - if "
            "'raise', then any error will immediately halt; if 'warn', then a "
            "warning will continue, then processing will continue on other "
            "lights or usda files"
        ),
    )
    return parser


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = get_parser()
    args = parser.parse_args()
    try:
        write_light_param_descriptions(args.path, recurse=args.recurse, errors=args.errors)
    except Exception:  # pylint: disable=broad-except

        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__" and not is_ipython():
    sys.exit(main())
