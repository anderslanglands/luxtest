# Problem Statement

The current specifications of the various UsdLux prims + attributes are imprecise or vague in many places, and as a result, actual implementations of them by various renderers have diverged, sometimes quite significantly.  For instance, here is Intel's [4004 Moore Lane](https://dpel.aswf.io/4004-moore-lane/) scene, with the same UsdLux lights defined, in 3 different renderers:

| Karma                                   | Arnold                                    | Omniverse RTX                                 |
| --------------------------------------- | ----------------------------------------- | --------------------------------------------- |
| ![4004 Moore Lane - Karma][moore-karma] | ![4004 Moore Lane - Arnold][moore-arnold] | ![4004 Moore Lane - Omniverse RTX][moore-rtx] |

# Solution

We need to update UsdLux to specify exactly what quantities should be emitted for each light and combination of its attributes so that lighting can be shared between applications and renderers.

A PR with proposals for these changes may be found here:
- https://github.com/PixarAnimationStudios/OpenUSD/pull/3182

Further, we propose adding a reference implementation of UsdLux support to hdEmbree, in a similar way that hdStorm provides a reference implementation of a Hydra Render Delegate.  A PR chain adding such an implementation can be found here:

- https://github.com/PixarAnimationStudios/OpenUSD/pull/3199


#  A Test Suite For UsdLux

Further, this repo aims to provide tooling to:
- generate standardized UsdLux test scenes (in .usda format)
- generate renders of these test scenes
- compare rendered images between different renderers

## Prerequisites

- Install Houdini
  - Apprentice editions will not work
  - Check RenderMan compatible versions:
    - RenderMan 26:
      - https://rmanwiki.pixar.com/display/RFH26/Installation+of+RenderMan+for+Houdini
      - > RenderMan for Houdini 26.0 supports: 20.0.653, 19.5.805, 19.0.720
      - > RenderMan for Houdini on Linux will only operate with the gcc9.3 houdini build.
  - Check Arnold compatible versions:
    - See below for download instructions, and check available builds
- Install RenderMan + RenderMan for Houdini
  - Register on pixar forums
    - https://renderman.pixar.com/forum/
  - Download:
    - https://renderman.pixar.com/install
- Install HtoA (Houdini to Arnold)
  - Purchase Arnold license, or sign up for free trial:
    - https://www.autodesk.com/products/arnold/overview
  - Download HtoA from [https://manage.autodesk.com/products/updates] (filter by "HtoA")

## Usage

### Automatically rendering all lights using hython
- Make sure the `bin` folder for houdini is on your `PATH`
- run `hython genhoudini.py`

### Manually rendering individual lights in Houdini GUI
- Open `luxtest.hip` in Houdini
- In the Solaris /stage pane, scroll down to the section corresponding to the
  lighting setup you wish to render:
  - distant
  - rect
  - sphere
  - disk
  - cylinder
  - dome
  - visibleRect
- Select the USD Render ROP corresponding to the renderer you wish to render
  - will be of format `render_{light}_{renderer}
  - ie, `render_rect_ris`
- In the parameters pane, click "Render to Disk"

## Renders repo

Result rendered images are available in a
[separate repo](https://github.com/pmolodo/luxtest_renders).  To add it to
this repo, first ensure "renders" subdir does not already exist, then from
the repo root, run:

```shell
git clone --filter=blob:none https://github.com/pmolodo/luxtest_renders renders
```


[moore-karma]: https://github.com/anderslanglands/light_comparison/blob/main/renders/moore-lane/moore-lane_karma.jpg?raw=true "Karma"
[moore-arnold]: https://github.com/anderslanglands/light_comparison/blob/main/renders/moore-lane/moore-lane_arnold.jpg?raw=true "Arnold"
[moore-rtx]: https://github.com/anderslanglands/light_comparison/blob/main/renders/moore-lane/moore-lane_rtx.jpg?raw=true "Omniverse RTX"
