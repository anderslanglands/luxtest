import inspect
import math
import os
import re
import sys

from typing import Iterable, NamedTuple, Optional, TypeAlias, Union

import hou

NodeOrRe: TypeAlias = Union[hou.Node, re.Pattern]
NodeOrReOrIterable = Union[NodeOrRe, Iterable[NodeOrRe]]


THIS_FILE = os.path.abspath(inspect.getsourcefile(lambda: None) or __file__)
THIS_DIR = os.path.dirname(THIS_FILE)

if THIS_DIR not in sys.path:
    sys.path.append(THIS_DIR)

import luxtest_const

###############################################################################
# Constants
###############################################################################

THIS_FILE = os.path.abspath(inspect.getsourcefile(lambda: None) or __file__)
THIS_DIR = os.path.dirname(THIS_FILE)

###############################################################################
# General Houdini Utilities
###############################################################################


def top_stage_nodes(type=""):
    nodes = hou.node("/stage").children()
    if type:
        if isinstance(type, str):
            type = lop_type(type)
        nodes = [x for x in nodes if x.type() == type]
    return nodes


RENDERER_SHORT_NAMES = {
    "BRAY_HdKarma": "karma",
    "HdArnoldRendererPlugin": "arnold",
    "HdPrmanLoaderRendererPlugin": "ris",
}


# Because dealing with encoded parm names (but with not-encoded-tuple-member-suffixes) is annoying...
# ie, you can't just reliably do hou.text.decode(parm.name())!
class ParmName(NamedTuple):
    tuplename: str
    suffix: str = ""

    def __str__(self):
        return self.encoded

    def __repr__(self):
        # want to get a compact repr...
        if self.suffix == "":
            return f"PN({self.tuplename!r})"
        return f"PN{tuple(self)!r}"

    @property
    def pretty(self):
        if self.suffix:
            return f"{self.tuplename},{self.suffix}"
        else:
            return self.tuplename

    @property
    def encoded_tuplename(self):
        return hou.text.encode(self.tuplename)

    @property
    def encoded(self):
        return self.encoded_tuplename + self.suffix

    @classmethod
    def from_parm(cls, parm: Union[hou.Parm, hou.ParmTuple]):
        if isinstance(parm, hou.ParmTuple):
            parm_tuple = parm
            parm = None
        else:
            parm_tuple = parm.tuple()
        encoded_tuplename = parm_tuple.name()
        if parm is None:
            suffix = ""
        else:
            encoded = parm.name()
            assert encoded.startswith(encoded_tuplename)
            suffix = encoded[len(encoded_tuplename) :]
        return cls(hou.text.decode(encoded_tuplename), suffix)


PN = ParmName


def pretty_parm_path(parm: hou.Parm):
    parmName = ParmName.from_parm(parm)
    return f"{parm.node().path()}/{parmName.pretty}"


def get_parm_tuple(node, name):
    parmTuple = node.parmTuple(name)
    if not parmTuple:
        parmTuple = node.parmTuple(hou.text.encode(name))
        if not parmTuple:
            # ok, it couldn't be easy - try tuple names...
            raise ValueError(f"node {node.path()!r} has no parmTuple {name!r}")
    return parmTuple


def get_parm(node, name, suffix=""):
    if isinstance(node, str):
        result = hou.node(node)
        if result:
            node = result
        else:
            result = get_light(node)
            if not result:
                raise ValueError(f"could not find node: {node}")
            node = result
    try:
        parmTuple = node.parmTuple(name)
    except ValueError:
        parmTuple = None
    if not parmTuple:
        if suffix:
            raise ValueError(
                f"could not find parmTuple for node {node.path()}: {name} (so cannot find suffix {suffix})"
            )
        # could have been given an encoded name with suffix...
        parm = node.parm(name)
        if parm:
            return parm
        # last ditch - try encoded?
        parm = node.parm(hou.text.encode(name))
        if parm:
            return parm
        raise ValueError(f"Could not find a parmTuple for node {node.path()} with name: {name}")
    if len(parmTuple) > 1:
        if not suffix:
            raise ValueError(f"{parmTuple.path()} was a parmTuple - specify a suffix, or use get_parm_tuple")
        full_encoded_name = parmTuple.name() + suffix
        parm = node.parm(full_encoded_name)
        if not parm:
            raise ValueError(
                f"Found parmTuple {parmTuple.name()} for node {node.path()}, but could not find with suffix {suffix}"
            )
        return parm

    if suffix:
        raise ValueError(
            f"Found parmTuple {parmTuple.name()} for node {node.path()}, but only had one member, so could not find"
            f" suffix {suffix}"
        )
    return parmTuple[0]


def get_renderer(node):
    return RENDERER_SHORT_NAMES[node.parm("renderer").eval()]


def lop_type(name):
    return hou.lopNodeTypeCategory().nodeType(name)


def base_type(nodetype):
    if isinstance(nodetype, hou.Node):
        nodetype = nodetype.type()
    return nodetype.namespaceOrder()[-1]


def is_light_type(nodetype):
    return base_type(nodetype) in ("light", "distantlight", "domelight")


def is_area_light_type(nodetype):
    return base_type(nodetype) == "light"


def is_light(node):
    return is_light_type(node.type())


def is_area_light(node):
    return is_area_light_type(node.type())


def get_nodes_referencing(node, include_self=False, node_refs=True, parm_refs=True):
    all_refs = set()
    if node_refs:
        all_refs.update(x.node() for x in node.parmsReferencingThis())
    if parm_refs:
        for parm in node.parms():
            all_refs.update(x.node() for x in parm.parmsReferencingThis())
    if not include_self:
        all_refs.discard(node)
    return all_refs


def make_parm_tuple_refs(tuple_name, source_node, dest_nodes):
    source_parm_tuple = get_parm_tuple(source_node, tuple_name)

    for dest_node in dest_nodes:
        dest_parm_tuple = get_parm_tuple(dest_node, source_parm_tuple.name())
        assert len(source_parm_tuple) == len(dest_parm_tuple)
        for source_parm, dest_parm in zip(source_parm_tuple, dest_parm_tuple):
            source_parm_name = pretty_parm_path(source_parm)
            dest_parm_name = pretty_parm_path(dest_parm)
            if dest_parm.getReferencedParm() == source_parm:
                print(f"{dest_parm_name} already connected to {source_parm_name} - skipped")
            else:
                ref_exp = dest_parm.referenceExpression(source_parm)
                dest_parm.setExpression(ref_exp, language=hou.exprLanguage.Hscript)
                print(f"{dest_parm_name} now references {source_parm_name}")


def get_all_animated_parms(root_node="/", include: NodeOrReOrIterable = (), exclude: NodeOrReOrIterable = ()):
    if isinstance(root_node, str):
        root_node = hou.node(root_node)
    all = []

    def make_matcher(obj: NodeOrRe):
        if isinstance(obj, hou.Node):
            return lambda x: x == obj
        elif isinstance(obj, re.Pattern):
            return lambda x: obj.search(x.path())
        raise TypeError(f"obj must be hou.Node or re.Pattern - got: {obj}")

    if include:
        if isinstance(include, (re.Pattern, hou.Node)):
            include = [include]
        include_matchers = [make_matcher(x) for x in include]

        def is_included(obj):
            return any(x(obj) for x in include_matchers)

    else:

        def is_included(obj):
            return True

    if exclude:
        if isinstance(exclude, (re.Pattern, hou.Node)):
            exclude = [exclude]
        exclude_matchers = [make_matcher(x) for x in exclude]

        def is_excluded(obj):
            return any(x(obj) for x in exclude_matchers)

    else:

        def is_excluded(obj):
            return False

    for node in (root_node,) + root_node.allSubChildren():
        if is_excluded(node) or not is_included(node):
            continue
        all.extend(parm for parm in node.parms() if len(parm.keyframes()) > 1)
    return all


def select_all_animated_parms(root_node="/", **kwargs):
    parms = get_all_animated_parms(root_node, **kwargs)
    for p in parms:
        p.setSelect(True)
    return parms


def get_keyframe_value(keyframe):
    if isinstance(keyframe, hou.StringKeyframe):
        return keyframe.expression()
    return keyframe.value()


def insert_anim_gap(frame, num_frames, include: Iterable[NodeOrRe] = (), exclude: Iterable[NodeOrRe] = ()):
    """Shifts all keyframes >= frame by num_frames.

    Sets new keyframe at the frame to keep animation constant
    during it (if needed)
    """
    to_shift = {}
    to_key = {}

    for parm in get_all_animated_parms(include=include, exclude=exclude):
        before_keys = parm.keyframesBefore(frame)
        after_keys = parm.keyframesAfter(frame)
        if before_keys and before_keys[-1].frame() == frame:
            if not after_keys or after_keys[0].frame() != frame:
                after_keys.insert(0, before_keys[-1])
            before_keys = before_keys[:-1]
        if not after_keys:
            # nothing to move, carry on!
            continue
        to_shift[parm] = after_keys
        if not before_keys:
            # no before keys, don't need a new keyframe
            continue
        # we have both before and after keys...
        before = before_keys[-1]
        after = after_keys[0]
        after_val = get_keyframe_value(after)
        if get_keyframe_value(before) == after_val:
            # constant value, don't need a new keyframe
            continue
        # different values - abort, don't want to insert gap in the middle
        # of an animated value change
        if not math.isclose(after.frame(), frame):
            raise RuntimeError(f"Cannot insert anim gap at frame {frame} - {parm.path()} has animation")
        new_keys = []
        for new_frame in (frame, frame + num_frames - 1):
            if isinstance(after, hou.StringKeyframe):
                keyframe = hou.StringKeyframe(after)
                keyframe.setFrame(new_frame)
            else:
                keyframe = hou.Keyframe(after_val, hou.frameToTime(new_frame))
                keyframe.setExpression("linear()")
            new_keys.append(keyframe)

        to_key[parm] = new_keys
    for parm, keys in to_shift.items():
        for key in keys:
            frame = key.frame()
            parm.deleteKeyframeAtFrame(frame)
            key.setFrame(frame + num_frames)
        parm.setKeyframes(keys)

    for parm, keys in to_key.items():
        parm.setKeyframes(keys)


def make_sphere_tuple_refs(tuple_name):
    sphere = hou.node("/stage/sphere_light")
    sphere_refs = [x for x in get_nodes_referencing(sphere) if is_light(x)]
    make_parm_tuple_refs(tuple_name, sphere, sphere_refs)


def get_connected_recursive(node, predicate, direction, visited=None):
    results = set()
    if predicate(node):
        results.add(node)
    if visited is None:
        visited = set([node])
    else:
        visited.add(node)
    if direction == "outputs":
        get_next = node.outputs
    elif direction == "inputs":
        get_next = node.inputs
    for other_node in get_next():
        if other_node not in visited:
            results.update(get_connected_recursive(other_node, predicate, direction, visited=visited))
    return results


def get_upstream(node, predicate):
    return get_connected_recursive(node, predicate, "inputs")


def get_downstream(node, predicate):
    return get_connected_recursive(node, predicate, "outputs")


def get_downstream_lights(node):
    return get_downstream(node, is_light)


def get_upstream_lights(node):
    return get_upstream(node, is_light)


def get_connected_lights(node):
    if is_light(node):
        return set([node])
    input_lights = get_upstream_lights(node)
    if input_lights:
        return input_lights
    return get_downstream_lights(node)


def get_rop_out_parm(node):
    if node.type() == lop_type("usd_rop"):
        return node.parm("lopoutput")
    elif node.type() == lop_type("usdrender_rop"):
        return node.parm("outputimage")
    else:
        raise TypeError(f"Unrecognized rop node type: {node} - {node.type()}")


def parm_at_default(parm):
    tuple_name = ParmName.from_parm(parm).tuplename
    missing = object()
    default = luxtest_const.DEFAULT_OVERRIDES.get(tuple_name, missing)
    if default is not missing:
        current = parm.eval()
        if isinstance(current, float) or isinstance(default, float):
            return math.isclose(current, default)
        return current == default
    return parm.isAtDefault()


def get_non_default_parms(nodeOrParms, frames: Optional[Iterable[Union[float, int]]] = None):
    if isinstance(nodeOrParms, hou.Node):
        parms = nodeOrParms.parms()
    else:
        parms = list(nodeOrParms)

    if frames is None:
        return set([x for x in parms if not parm_at_default(x)])
    orig_frame = hou.frame()
    non_default = None
    try:
        for frame in frames:
            hou.setFrame(frame)
            current_non_defaults = get_non_default_parms(parms)
            if non_default is None:
                non_default = current_non_defaults
            else:
                non_default.update(current_non_defaults)
    finally:
        hou.setFrame(orig_frame)
    return non_default


def parmgrep(node, pattern):
    regex = re.compile(pattern, re.IGNORECASE)
    parms = parm_tuple_dict(node)
    return {name: node for name, node in parms.items() if regex.search(name) or regex.search(hou.text.encode(name))}


def parm_tuple_dict(node, controls=False):
    """Returns a dict from decoded parm tuple name to the parmTuple"""
    pairs = [(hou.text.decode(p.name()), p) for p in node.parmTuples()]
    if not controls:
        pairs = [(name, node) for name, node in pairs if not name.endswith("_control")]
    pairs.sort(key=lambda pair: pair[0])
    return dict(pairs)


def input_parm_tuples(node, controls=False):
    all_parms_dict = parm_tuple_dict(node, controls=controls)
    return {name: node for name, node in all_parms_dict.items() if name.startswith("inputs:")}


def houdini_range(start, stop=None, step=1):
    if stop is None:
        start = 0
        stop = start - 1
    current = start
    while current <= stop:
        yield current
        current += step


def get_frames(node):
    start = node.parm("f1").eval()
    stop = node.parm("f2").eval()
    step = node.parm("f3").eval()
    return houdini_range(start, stop, step)


###############################################################################
# Naming Utils
###############################################################################

NODE_BASE_TYPE_TO_CATEGORY = {
    "usd_rop": "usd_rop",
    "usdrender_rop": "render",
    "camera": "camera",
    "distantlight": "light",
    "domelight": "light",
    "light": "light",
    "editproperties": "editproperties",
    "xform": "xform",
}


def node_category(node):
    base = base_type(node)
    return NODE_BASE_TYPE_TO_CATEGORY.get(base, base)


LIGHT_NAME_RE = re.compile("^(?P<name>.*)_light$")


def parse_light_name(node_or_name):
    if isinstance(node_or_name, hou.Node):
        nodename = node_or_name.name()
    else:
        nodename = node_or_name
    return LIGHT_NAME_RE.match(nodename).group("name")


def get_light(name):
    return hou.node(f"/stage/{name}_light")


def prim_basename(prim_name: str):
    return prim_name.rstrip("/").rsplit("/", 1)[-1]


def get_rop_override_cam(rop):
    return prim_basename(rop.parm("override_camera").eval())


def get_standardized_name(node, associated_light_node):
    light_name = parse_light_name(associated_light_node)
    category = node_category(node)
    if category == "light":
        return f"{light_name}_light"
    elif category == "render":
        renderer = get_renderer(node)
        cam = get_rop_override_cam(node)
        if cam:
            cam = f"_{cam}"
        return f"{category}{cam}_{renderer}_{light_name}"
    elif category == "camera":
        cam_node_type = {
            0: "edit",
            1: "create",
            2: "forceedit",
        }[node.parm("createprims").eval()]
        if cam_node_type == "create":
            prim_path = node.parm("primpath").eval()
        else:
            prim_path = node.parm("primpattern").eval()
        prim_name = prim_basename(prim_path)
        return f"{category}_{cam_node_type}_{prim_name}_{light_name}"
    elif category == "xform":
        prim_name = prim_basename(node.parm("primpattern").eval())
        return f"{category}_{prim_name}_{light_name}"
    elif category == "sopcreate":
        prim_name = prim_basename(node.parm("pathprefix").eval())
        return f"{category}_{prim_name}_{light_name}"
    elif category == "assignmaterial":
        prim_name = prim_basename(node.parm("primpattern1").eval())
        return f"{category}_{prim_name}_{light_name}"
    else:
        return f"{category}_{light_name}"


def standardize_node_names(dry_run=True):
    renames = []
    for node in top_stage_nodes():
        lights = get_connected_lights(node)
        if len(lights) != 1:
            continue
        light = lights.pop()
        new_name = get_standardized_name(node, light)
        old_name = node.name()
        if old_name != new_name:
            renames.append((old_name, new_name, node))
    print()
    print("=" * 80)
    if not renames:
        print("Found no nodes to rename")
        return
    renames.sort()
    print(f"Found {len(renames)} nodes to rename:")
    print("=" * 80)
    for old_name, new_name, node in renames:
        print(f"rename: {old_name} => {new_name}")
        if not dry_run:
            node.setName(new_name)
    print("=" * 80)
    if dry_run:
        print("dry_run=True - nothing changed - to change names, use:")
        print("  standardize_node_names(dry_run=False)")


def get_standardized_output_path(node, light_node):
    light_name = parse_light_name(light_node)
    if node.type() == lop_type("usd_rop"):
        return f"$HIP/usd/{light_name}.usda"
    elif node.type() == lop_type("usdrender_rop"):
        renderer = get_renderer(node)
        cam = get_rop_override_cam(node)
        if cam:
            cam = f".{cam}"
        return f"$HIP/renders/{renderer}/{light_name}-{renderer}{cam}.$F4.exr"


def standardize_output_names(dry_run=True):
    renames = []
    rop_nodes = [x for x in top_stage_nodes() if isinstance(x, hou.RopNode)]
    for rop in rop_nodes:
        lights = get_connected_lights(rop)
        if len(lights) != 1:
            print(f"found rop that couldn't be associated with one light: {rop} - {lights}")
            continue
        light = lights.pop()
        new_output_path = get_standardized_output_path(rop, light)
        parm = get_rop_out_parm(rop)
        old_output_path = parm.rawValue()
        if old_output_path != new_output_path:
            renames.append((rop.name(), parm, old_output_path, new_output_path))
    print()
    print("=" * 80)
    if not renames:
        print("Found no node output paths to change")
        return
    renames.sort()
    print(f"Found {len(renames)} nodes with output paths to change:")
    print("=" * 80)
    for node_name, parm, old_output_path, new_output_path in renames:
        print(f"rename output for {node_name}:")
        print(f"  {old_output_path}")
        print(f"  {new_output_path}")
        if not dry_run:
            parm.set(new_output_path)
    print("=" * 80)
    if dry_run:
        print("dry_run=True - nothing changed - to change names, use:")
        print("  standardize_output_names(dry_run=False)")


###############################################################################
# Summaries
###############################################################################

SUMMARY_LINE_RE = re.compile("^\d+(?:-\d+)?:\s+.+", re.MULTILINE)


def reset_net_box_summaries(dry_run=True):
    if THIS_DIR not in sys.path:
        sys.path.append(THIS_DIR)

    import genLightParamDescriptions

    param_descriptions = genLightParamDescriptions.read_descriptions()

    stage = hou.node("/stage")

    to_update = []
    for box in stage.networkBoxes():
        # find the light
        lights = [x for x in box.nodes() if is_light(x)]
        if not lights:
            continue
        if len(lights) > 1:
            raise RuntimeError("more than one light? oh noes!")
        light = lights[0]
        light_name = parse_light_name(light)
        usd_light_name = light_name.replace("-", "_")

        # now find the sticky note with the summary
        stickies = [x for x in box.stickyNotes() if SUMMARY_LINE_RE.search(x.text())]
        if len(stickies) != 1:
            raise RuntimeError(f"can't find right sticky for net box for light {light_name}")
        sticky = stickies[0]

        # now get the new summary text
        desc = param_descriptions[usd_light_name]
        try:
            summary = genLightParamDescriptions.summarize_light(light_name, desc)
        except Exception:
            print(desc)
            print(f"error summarizing light: {light_name}")
            raise
        if not summary:
            continue

        if sticky.text() != summary:
            to_update.append((light_name, sticky, summary))

    print()
    print("=" * 80)
    if not to_update:
        print("Found no network box summaries to update")
        return
    to_update.sort()
    print(f"Found {len(to_update)} network box summaries to update:")
    print("=" * 80)
    for light_name, sticky, summary in to_update:
        print()
        print(f"{light_name}:")
        print(summary)
        if not dry_run:
            sticky.setText(summary)
    print("=" * 80)
    if dry_run:
        print("dry_run=True - nothing changed - to change summaries, use:")
        print("  reset_net_box_summaries(dry_run=False)")
