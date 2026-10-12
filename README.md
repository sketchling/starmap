# StarMap Generator (Blender 5)

Accurate, controllable starmaps. Brightest stars in the real night sky become
tiny cubes coloured by colour temperature (B-V → Teff → blackbody RGB),
placed by observer location + UTC date/time.

Two lat/long paths (same sky, same mapping):
1. **3D (recommended):** Generate → Setup lat/long camera → Render (F12).
   Camera is an equirectangular panorama at the origin, so the render is a
   2:1 lat/long starmap.
2. **2D (fast/math):** "Make 2D lat/long image" paints the same sky directly
   into a Blender image (`StarMap_Equirect`), no render needed.

Mapping (both paths): U = az/360 + 0.5 (U=0.5 faces true north, U=0/1 seam
faces south, east appears right-of-centre as seen facing north),
V = (alt+90)/180 (V=1 zenith, V=0.5 horizon, V=0 nadir). Verified
pixel-accurate against Cycles renders (Vega/Capella land within 1px).

> Tip: the lat/long camera sees the full 360° from the origin, so start
> from an empty scene (or hide other objects) — anything near the origin
> (e.g. the default cube) will block the sky.

## Install

Blender 5 → Edit → Preferences → Add-ons → Install from Disk → select the
`starmap_generator` folder (or its .zip) → enable "StarMap Generator".
Panel: 3D Viewport → Sidebar (N) → StarMap. Pick a city preset (or type
lat/long by hand — editing the numbers flips the menu back to Custom),
set UTC date/time, star count, and hit Generate. The world background is
set to black automatically; cardinal markers and name labels default off
for a clean sky.

## Accuracy notes

- Catalogue: HYG v4.2 (Hipparcos/Yale/Gliese), J2000, top 3000 by Vmag.
- Precession J2000 → mean of date, GMST/LST, Alt/Az: good to ~arcminute
  for 1900–2100. Proper motion / nutation / aberration / refraction ignored
  (sub-degree, fine for art and previz, not for navigation).
- `Hide below horizon` = planetarium view. Turn it off for the full
  celestial sphere.
- Distances: `Celestial shell` puts everything at one radius (cleanest
  lat/long). `Scaled true distance` uses a tiny fraction of real parsec
  distances (units-per-parsec) while preserving angular cube sizes.

## Colours

B-V → Teff (Ballesteros 2012) → sRGB blackbody (Tanner Helland) → linear.
Uncheck "Colour by temperature" for white stars.

## License

Addon code: MIT (see LICENSE). Star catalogue (`stars.csv`): derived from
the HYG Database v4.2, CC BY-SA 4.0 — see `starmap_generator/ATTRIBUTION.txt`.
