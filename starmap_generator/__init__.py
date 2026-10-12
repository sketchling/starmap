bl_info = {
    "name": "StarMap Generator",
    "author": "StarMap",
    "version": (1, 0, 0),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > StarMap",
    "description": "Accurate controllable starmap: brightest stars as colour-temperature cubes, placed by date/time + observer location. Renders to lat/long (equirectangular).",
    "category": "3D View",
}

# Star catalogue: derived from the HYG Database v4.2 (Hipparcos + Yale Bright
# Star + Gliese), (c) Astronexus / David Nash, CC BY-SA 4.0.
# See https://codeberg.org/astronexus/hyg and ATTRIBUTION.txt.
# This addon ships only the brightest 3000 stars (mag <= ~5.5) with
# name, RA (hours, J2000), Dec (deg, J2000), Vmag, B-V, distance (pc).

import bpy
import csv
import math
import os
from datetime import datetime, timezone

ADDON_DIR = os.path.dirname(__file__)
STAR_CSV = os.path.join(ADDON_DIR, "stars.csv")
COLLECTION_NAME = "StarMap"
BASE_MESH_NAME = "StarMap_CubeMesh"


# ---------------------------------------------------------------------------
# City presets (lat deg N, lon deg E)
# ---------------------------------------------------------------------------

CITY_COORDS = {
    "LONDON": (51.5074, -0.1278),
    "PARIS": (48.8566, 2.3522),
    "BERLIN": (52.5200, 13.4050),
    "MADRID": (40.4168, -3.7038),
    "ROME": (41.9028, 12.4964),
    "REYKJAVIK": (64.1466, -21.9426),
    "MOSCOW": (55.7558, 37.6173),
    "CAIRO": (30.0444, 31.2357),
    "LAGOS": (6.5244, 3.3792),
    "NAIROBI": (-1.2921, 36.8219),
    "CAPE_TOWN": (-33.9249, 18.4241),
    "DUBAI": (25.2048, 55.2708),
    "MUMBAI": (19.0760, 72.8777),
    "BANGKOK": (13.7563, 100.5018),
    "SINGAPORE": (1.3521, 103.8198),
    "HONG_KONG": (22.3193, 114.1694),
    "BEIJING": (39.9042, 116.4074),
    "SEOUL": (37.5665, 126.9780),
    "TOKYO": (35.6762, 139.6503),
    "SYDNEY": (-33.8688, 151.2093),
    "AUCKLAND": (-36.8485, 174.7633),
    "ANCHORAGE": (61.2181, -149.9003),
    "SAN_FRANCISCO": (37.7749, -122.4194),
    "LOS_ANGELES": (34.0522, -118.2437),
    "CHICAGO": (41.8781, -87.6298),
    "NEW_YORK": (40.7128, -74.0060),
    "TORONTO": (43.6532, -79.3832),
    "MEXICO_CITY": (19.4326, -99.1332),
    "SAO_PAULO": (-23.5558, -46.6396),
    "BUENOS_AIRES": (-34.6037, -58.3816),
    "HONOLULU": (21.3099, -157.8581),
}

CITY_ITEMS = (
    ("CUSTOM", "Custom (manual)", "Type latitude/longitude by hand"),
    ("LONDON", "London, UK", ""),
    ("PARIS", "Paris, France", ""),
    ("BERLIN", "Berlin, Germany", ""),
    ("MADRID", "Madrid, Spain", ""),
    ("ROME", "Rome, Italy", ""),
    ("REYKJAVIK", "Reykjavik, Iceland", ""),
    ("MOSCOW", "Moscow, Russia", ""),
    ("CAIRO", "Cairo, Egypt", ""),
    ("LAGOS", "Lagos, Nigeria", ""),
    ("NAIROBI", "Nairobi, Kenya", ""),
    ("CAPE_TOWN", "Cape Town, South Africa", ""),
    ("DUBAI", "Dubai, UAE", ""),
    ("MUMBAI", "Mumbai, India", ""),
    ("BANGKOK", "Bangkok, Thailand", ""),
    ("SINGAPORE", "Singapore", ""),
    ("HONG_KONG", "Hong Kong", ""),
    ("BEIJING", "Beijing, China", ""),
    ("SEOUL", "Seoul, South Korea", ""),
    ("TOKYO", "Tokyo, Japan", ""),
    ("SYDNEY", "Sydney, Australia", ""),
    ("AUCKLAND", "Auckland, New Zealand", ""),
    ("ANCHORAGE", "Anchorage, USA", ""),
    ("SAN_FRANCISCO", "San Francisco, USA", ""),
    ("LOS_ANGELES", "Los Angeles, USA", ""),
    ("CHICAGO", "Chicago, USA", ""),
    ("NEW_YORK", "New York, USA", ""),
    ("TORONTO", "Toronto, Canada", ""),
    ("MEXICO_CITY", "Mexico City, Mexico", ""),
    ("SAO_PAULO", "Sao Paulo, Brazil", ""),
    ("BUENOS_AIRES", "Buenos Aires, Argentina", ""),
    ("HONOLULU", "Honolulu, USA", ""),
)


_APPLYING_CITY_PRESET = False


def _update_city(self, context):
    coords = CITY_COORDS.get(self.city_preset)
    if coords is None:  # CUSTOM: leave lat/lon alone
        return
    lat, lon = coords
    global _APPLYING_CITY_PRESET
    _APPLYING_CITY_PRESET = True
    try:
        if abs(self.latitude - lat) > 1e-9:
            self.latitude = lat
        if abs(self.longitude - lon) > 1e-9:
            self.longitude = lon
    finally:
        _APPLYING_CITY_PRESET = False


def _update_latlon(self, context):
    # hand-edited coordinates no longer match a preset -> show Custom
    if _APPLYING_CITY_PRESET or self.city_preset == "CUSTOM":
        return
    coords = CITY_COORDS.get(self.city_preset)
    if coords is None:
        return
    if abs(self.latitude - coords[0]) > 1e-6 or abs(self.longitude - coords[1]) > 1e-6:
        self.city_preset = "CUSTOM"


# ---------------------------------------------------------------------------
# Astronomy core (pure python, no dependencies)
# ---------------------------------------------------------------------------

def julian_date(year, month, day, hour=0, minute=0, second=0.0):
    """Meeus Julian Date from UTC calendar date."""
    if month <= 2:
        year -= 1
        month += 12
    A = year // 100
    B = 2 - A + A // 4
    frac = (hour + minute / 60.0 + second / 3600.0) / 24.0
    jd = (math.floor(365.25 * (year + 4716))
          + math.floor(30.6001 * (month + 1))
          + day + frac + B - 1524.5)
    return jd


def gmst_degrees(jd):
    """Greenwich Mean Sidereal Time in degrees (IAU, accurate to <<1 arcmin)."""
    T = (jd - 2451545.0) / 36525.0
    gmst = (280.46061837
            + 360.98564736629 * (jd - 2451545.0)
            + 0.000387933 * T * T
            - T * T * T / 38710000.0)
    return gmst % 360.0


def precess_j2000_to_mean(ra_hours, dec_deg, jd):
    """Precess J2000 RA/Dec to mean equinox of date (Meeus low-precision).

    Returns (ra_hours_mean, dec_deg_mean). Accurate to ~arcminute for 1900-2100.
    """
    T = (jd - 2451545.0) / 36525.0
    # arcseconds -> radians
    arcsec = math.pi / (180.0 * 3600.0)
    zeta = (2306.2181 * T + 0.30188 * T * T + 0.017998 * T * T * T) * arcsec
    z = (2306.2181 * T + 1.09468 * T * T + 0.018203 * T * T * T) * arcsec
    theta = (2004.3109 * T - 0.42665 * T * T - 0.041833 * T * T * T) * arcsec
    ra = math.radians(ra_hours * 15.0)
    dec = math.radians(dec_deg)
    x0 = math.cos(dec) * math.cos(ra)
    y0 = math.cos(dec) * math.sin(ra)
    z0 = math.sin(dec)
    # R = Rz(-z) * Ry(theta) * Rz(-zeta)
    czeta, szeta = math.cos(zeta), math.sin(zeta)
    x1 = czeta * x0 + szeta * y0
    y1 = -szeta * x0 + czeta * y0
    z1 = z0
    cth, sth = math.cos(theta), math.sin(theta)
    x2 = cth * x1 - sth * z1
    y2 = y1
    z2 = sth * x1 + cth * z1
    cz, sz = math.cos(z), math.sin(z)
    x3 = cz * x2 + sz * y2
    y3 = -sz * x2 + cz * y2
    z3 = z2
    ra_m = math.atan2(y3, x3) % (2.0 * math.pi)
    dec_m = math.asin(max(-1.0, min(1.0, z3)))
    return (math.degrees(ra_m) / 15.0) % 24.0, math.degrees(dec_m)


def equatorial_to_horizontal(ra_hours_mean, dec_deg_mean, lat_deg, lst_deg):
    """Mean RA/Dec -> Alt/Az. Az measured from true north, eastward (0=N,90=E)."""
    H = math.radians((lst_deg - ra_hours_mean * 15.0 + 540.0) % 360.0 - 180.0)
    dec = math.radians(dec_deg_mean)
    lat = math.radians(lat_deg)
    sin_alt = (math.sin(dec) * math.sin(lat)
               + math.cos(dec) * math.cos(lat) * math.cos(H))
    sin_alt = max(-1.0, min(1.0, sin_alt))
    alt = math.asin(sin_alt)
    cos_alt = math.cos(alt)
    if abs(cos_alt) < 1e-9:
        return 90.0 if sin_alt > 0 else -90.0, 0.0
    sin_az = -math.cos(dec) * math.sin(H) / cos_alt
    cos_az = (math.sin(dec) - math.sin(alt) * math.sin(lat)) / (cos_alt * math.cos(lat))
    cos_az = max(-1.0, min(1.0, cos_az))
    az = math.degrees(math.atan2(sin_az, cos_az)) % 360.0
    return math.degrees(alt), az


def altaz_to_blender(alt_deg, az_deg, radius):
    """Observer-centric Alt/Az -> Blender coords.

    Blender is right-handed with Z up: with East=+X and Up=+Z, North=+Y
    (E x N = U). Az measured from true north, eastward.
    """
    alt = math.radians(alt_deg)
    az = math.radians(az_deg)
    ca = math.cos(alt)
    return (radius * ca * math.sin(az),
            radius * ca * math.cos(az),
            radius * math.sin(alt))


def sun_radec_approx(jd):
    """Low-precision Sun apparent RA/Dec (deg->hours). Good to ~0.01 deg."""
    n = jd - 2451545.0
    L = math.radians((280.460 + 0.9856474 * n) % 360.0)
    g = math.radians((357.528 + 0.9856003 * n) % 360.0)
    lam = L + math.radians(1.915) * math.sin(g) + math.radians(0.020) * math.sin(2.0 * g)
    eps = math.radians(23.439 - 0.0000004 * n)
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam)) % (2.0 * math.pi)
    dec = math.asin(max(-1.0, min(1.0, math.sin(eps) * math.sin(lam))))
    return (math.degrees(ra) / 15.0) % 24.0, math.degrees(dec)


# ---------------------------------------------------------------------------
# Colour temperature
# ---------------------------------------------------------------------------

def bv_to_teff(bv):
    """B-V -> effective temperature (Ballesteros 2012)."""
    bv = max(-0.4, min(2.0, bv))
    t = 4600.0 * (1.0 / (0.92 * bv + 1.7) + 1.0 / (0.92 * bv + 0.62))
    return max(1500.0, min(40000.0, t))


def teff_to_srgb(teff):
    """Tanner Helland blackbody approx -> sRGB 0..1 tuple."""
    t = teff / 100.0
    # red
    if t <= 66:
        r = 255.0
    else:
        r = 329.698727446 * math.pow(t - 60.0, -0.1332047592)
    # green
    if t <= 66:
        g = 99.4708025861 * math.log(max(1.0, t)) - 161.1195681661
    else:
        g = 288.1221695283 * math.pow(t - 60.0, -0.0755148492)
    # blue
    if t >= 66:
        b = 255.0
    elif t <= 19:
        b = 0.0
    else:
        b = 138.5177312231 * math.log(t - 10.0) - 305.0447927307
    r = max(0.0, min(255.0, r)) / 255.0
    g = max(0.0, min(255.0, g)) / 255.0
    b = max(0.0, min(255.0, b)) / 255.0
    return (r, g, b)


def srgb_to_linear(c):
    if c <= 0.04045:
        return c / 12.92
    return math.pow((c + 0.055) / 1.055, 2.4)


def bv_to_linear_rgb(bv):
    r, g, b = teff_to_srgb(bv_to_teff(bv))
    return (srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b))


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

def load_stars(limit):
    stars = []
    with open(STAR_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                stars.append({
                    "name": row["name"],
                    "ra": float(row["ra_hours"]),
                    "dec": float(row["dec_deg"]),
                    "mag": float(row["mag"]),
                    "bv": float(row["bv"]),
                    "dist": float(row["dist_pc"]),
                })
            except (ValueError, KeyError):
                continue
    stars.sort(key=lambda s: s["mag"])
    return stars[:max(1, min(limit, len(stars)))]


# ---------------------------------------------------------------------------
# Blender helpers (no bpy.ops -> works headless)
# ---------------------------------------------------------------------------

def get_collection():
    coll = bpy.data.collections.get(COLLECTION_NAME)
    if coll is None:
        coll = bpy.data.collections.new(COLLECTION_NAME)
        bpy.context.scene.collection.children.link(coll)
    return coll


def ensure_black_world():
    """Make the scene background pure black so the starfield reads clearly."""
    scene = bpy.context.scene
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("StarMap_World")
        scene.world = world
    if not world.use_nodes:
        world.use_nodes = True
    for node in world.node_tree.nodes:
        if node.type == "BACKGROUND":
            node.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
            node.inputs["Strength"].default_value = 1.0
            break


def get_base_cube_mesh():
    mesh = bpy.data.meshes.get(BASE_MESH_NAME)
    if mesh is not None and len(mesh.vertices) == 8:
        return mesh
    if mesh is None:
        mesh = bpy.data.meshes.new(BASE_MESH_NAME)
    s = 0.5
    verts = [(-s, -s, -s), (s, -s, -s), (s, s, -s), (-s, s, -s),
             (-s, -s, s), (s, -s, s), (s, s, s), (-s, s, s)]
    faces = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    mesh.clear_geometry()
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    return mesh


def make_emission_material(name, rgb_linear, strength):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new(type="ShaderNodeOutputMaterial")
    out.location = (300, 0)
    emis = nodes.new(type="ShaderNodeEmission")
    emis.location = (0, 0)
    emis.inputs["Color"].default_value = (rgb_linear[0], rgb_linear[1], rgb_linear[2], 1.0)
    emis.inputs["Strength"].default_value = float(strength)
    links.new(emis.outputs["Emission"], out.inputs["Surface"])
    return mat


def star_size(mag, base_size, size_by_mag):
    if not size_by_mag:
        return base_size
    factor = math.pow(10.0, -0.15 * mag)
    factor = max(0.25, min(2.5, factor))
    return base_size * factor


def star_strength(mag, base_emission, brightness_by_mag):
    if not brightness_by_mag:
        return base_emission
    s = base_emission * math.pow(10.0, -0.4 * mag)
    return max(0.05, min(base_emission * 5.0, s))


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class StarMapSettings(bpy.types.PropertyGroup):
    city_preset: bpy.props.EnumProperty(
        name="City preset", description="Set observer location from a major city (or type coordinates manually)",
        items=CITY_ITEMS, default="LONDON", update=_update_city)
    latitude: bpy.props.FloatProperty(
        name="Latitude", description="Observer latitude, degrees north (+N / -S)",
        default=51.5074, min=-90.0, max=90.0, update=_update_latlon)
    longitude: bpy.props.FloatProperty(
        name="Longitude", description="Observer longitude, degrees east (+E / -W)",
        default=-0.1278, min=-180.0, max=180.0, update=_update_latlon)
    year: bpy.props.IntProperty(name="Year (UTC)", default=2026, min=1900, max=2100)
    month: bpy.props.IntProperty(name="Month (UTC)", default=10, min=1, max=12)
    day: bpy.props.IntProperty(name="Day (UTC)", default=11, min=1, max=31)
    hour: bpy.props.IntProperty(name="Hour (UTC)", default=22, min=0, max=23)
    minute: bpy.props.IntProperty(name="Minute (UTC)", default=0, min=0, max=59)

    num_stars: bpy.props.IntProperty(
        name="Number of stars", description="Brightest N stars in the real night sky (sorted by V magnitude)",
        default=1200, min=10, max=3000)
    sphere_radius: bpy.props.FloatProperty(
        name="Sphere radius", description="Celestial shell radius in Blender units (camera sits at origin)",
        default=1000.0, min=10.0, max=10000.0)

    placement_mode: bpy.props.EnumProperty(
        name="Distances",
        description="SHELL: all stars on one celestial sphere (best for lat/long renders). TRUE: scaled real parsec distances",
        items=[("SHELL", "Celestial shell", "All stars at sphere radius"),
               ("TRUE", "Scaled true distance", "Radius = dist_pc * units-per-parsec")],
        default="SHELL")
    distance_scale: bpy.props.FloatProperty(
        name="Units per parsec", description="Only for scaled-true-distance mode (tiny fraction of real distance)",
        default=5.0, min=0.05, max=200.0)

    base_size: bpy.props.FloatProperty(
        name="Cube size", description="Base cube edge length in Blender units",
        default=4.0, min=0.05, max=30.0)
    size_by_mag: bpy.props.BoolProperty(
        name="Size by magnitude", description="Brighter stars get bigger cubes", default=True)
    base_emission: bpy.props.FloatProperty(
        name="Emission", description="Base emission strength (brightest-star reference)",
        default=8.0, min=0.1, max=100.0)
    brightness_by_mag: bpy.props.BoolProperty(
        name="Brightness by magnitude", description="Physical Pogson scaling (2.512x per magnitude)", default=True)
    color_by_temp: bpy.props.BoolProperty(
        name="Colour by temperature", description="Blackbody colour from B-V index; off = white",
        default=True)

    hide_below_horizon: bpy.props.BoolProperty(
        name="Hide below horizon", description="Only place stars above the horizon (planetarium-accurate). Off = full celestial sphere",
        default=True)
    show_cardinals: bpy.props.BoolProperty(
        name="Cardinal labels (N/E/S/W)", default=False)
    label_brightest: bpy.props.IntProperty(
        name="Name labels", description="Text labels for the N brightest placed stars (0 = off)",
        default=0, min=0, max=30)
    show_sun: bpy.props.BoolProperty(
        name="Include Sun disc", description="Approximate Sun position for the given date/time (useful to check daytime)",
        default=False)

    image_width: bpy.props.IntProperty(
        name="2D image width", description="Width of direct mathematical equirectangular image (height = width/2)",
        default=2048, min=512, max=8192)


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------

def compute_sky(st, stars):
    jd = julian_date(st.year, st.month, st.day, st.hour, st.minute)
    lst = (gmst_degrees(jd) + st.longitude) % 360.0
    placed = []
    for s in stars:
        ra_m, dec_m = precess_j2000_to_mean(s["ra"], s["dec"], jd)
        alt, az = equatorial_to_horizontal(ra_m, dec_m, st.latitude, lst)
        if st.hide_below_horizon and alt < 0.0:
            continue
        if st.placement_mode == "TRUE":
            r = s["dist"] * st.distance_scale
            r = max(st.sphere_radius * 0.05, min(st.sphere_radius * 5.0, r))
        else:
            r = st.sphere_radius
        placed.append({"star": s, "alt": alt, "az": az, "r": r,
                       "ra_mean": ra_m, "dec_mean": dec_m})
    return jd, lst, placed


def clear_starmap():
    coll = bpy.data.collections.get(COLLECTION_NAME)
    if coll is not None:
        for ob in list(coll.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        # unlink + remove collection if empty of users
        try:
            bpy.context.scene.collection.children.unlink(coll)
        except RuntimeError:
            pass
        # remove if no users left
        if coll.users == 0:
            bpy.data.collections.remove(coll)
    # clean orphan star materials/meshes from previous runs
    for mat in list(bpy.data.materials):
        if (mat.name.startswith("Star_") or mat.name.startswith("StarMap_")) and mat.users == 0:
            bpy.data.materials.remove(mat)


def generate_starmap(st):
    clear_starmap()
    ensure_black_world()
    coll = get_collection()
    mesh = get_base_cube_mesh()
    # one slot on the shared mesh; each object overrides it (link='OBJECT')
    # so 3000 stars can share one mesh but keep individual colours.
    if len(mesh.materials) == 0:
        mesh.materials.append(None)
    stars = load_stars(st.num_stars)
    jd, lst, placed = compute_sky(st, stars)

    for i, p in enumerate(placed):
        s = p["star"]
        x, y, z = altaz_to_blender(p["alt"], p["az"], p["r"])
        size = star_size(s["mag"], st.base_size, st.size_by_mag)
        if st.placement_mode == "TRUE":
            # keep angular size constant regardless of true distance
            size *= p["r"] / st.sphere_radius
        if st.color_by_temp:
            rgb = bv_to_linear_rgb(s["bv"])
        else:
            rgb = (1.0, 1.0, 1.0)
        strength = star_strength(s["mag"], st.base_emission, st.brightness_by_mag)
        safe = "".join(c if (c.isalnum() or c in " _-") else "_" for c in s["name"])[:40] or f"star_{i}"
        mat = make_emission_material(f"Star_{i:04d}_{safe}", rgb, strength)
        ob = bpy.data.objects.new(f"Star_{i:04d}_{safe}", mesh)
        ob.location = (x, y, z)
        ob.scale = (size, size, size)
        ob.material_slots[0].link = "OBJECT"
        ob.material_slots[0].material = mat
        ob["starmap_name"] = s["name"]
        ob["starmap_mag"] = s["mag"]
        ob["starmap_bv"] = s["bv"]
        ob["starmap_alt"] = p["alt"]
        ob["starmap_az"] = p["az"]
        ob["starmap_ra_j2000_h"] = s["ra"]
        ob["starmap_dec_j2000"] = s["dec"]
        coll.objects.link(ob)

    # optional Sun
    if st.show_sun:
        ra_sun, dec_sun = sun_radec_approx(jd)
        # sun RA is already apparent-of-date approx; precession not needed
        alt, az = equatorial_to_horizontal(ra_sun, dec_sun, st.latitude, lst)
        if not (st.hide_below_horizon and alt < 0.0):
            x, y, z = altaz_to_blender(alt, az, st.sphere_radius * 0.999)
            mat = make_emission_material("StarMap_Sun", (1.0, 0.85, 0.65), st.base_emission * 4.0)
            ob = bpy.data.objects.new("StarMap_Sun", mesh)
            ob.location = (x, y, z)
            ob.scale = (st.base_size * 3.0,) * 3
            ob.material_slots[0].link = "OBJECT"
            ob.material_slots[0].material = mat
            ob["starmap_name"] = "Sun"
            ob["starmap_alt"] = alt
            ob["starmap_az"] = az
            coll.objects.link(ob)

    # cardinal labels
    if st.show_cardinals:
        for label, az in (("N", 0.0), ("E", 90.0), ("S", 180.0), ("W", 270.0)):
            x, y, z = altaz_to_blender(3.0, az, st.sphere_radius * 0.995)
            curve = bpy.data.curves.new(f"StarMap_{label}", type="FONT")
            curve.body = label
            curve.size = st.sphere_radius * 0.03
            mat = make_emission_material(f"StarMap_Mat_{label}", (0.7, 0.9, 1.0), 2.0)
            ob = bpy.data.objects.new(f"StarMap_{label}", curve)
            ob.location = (x, y, z)
            ob.active_material = mat
            coll.objects.link(ob)

    # name labels for brightest placed stars
    n = min(st.label_brightest, len(placed))
    for k in range(n):
        p = placed[k]
        s = p["star"]
        if not s["name"]:
            continue
        x, y, z = altaz_to_blender(p["alt"], p["az"], p["r"] * 1.015 + st.base_size)
        curve = bpy.data.curves.new(f"StarMap_Lbl_{k}", type="FONT")
        curve.body = s["name"]
        curve.size = max(1.0, st.sphere_radius * 0.012)
        mat = make_emission_material(f"StarMap_Mat_Lbl_{k}", (1.0, 1.0, 1.0), 1.5)
        ob = bpy.data.objects.new(f"StarMap_Lbl_{k}_{s['name']}"[:60], curve)
        ob.location = (x, y, z)
        ob.active_material = mat
        coll.objects.link(ob)

    return jd, lst, placed


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class STARMAP_OT_generate(bpy.types.Operator):
    bl_idname = "starmap.generate"
    bl_label = "Generate StarMap"
    bl_description = "Build colour-temperature star cubes for date/time + location"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        st = context.scene.starmap_settings
        # basic date sanity
        try:
            datetime(st.year, st.month, st.day, st.hour, st.minute)
        except ValueError as e:
            self.report({"ERROR"}, f"Invalid date/time: {e}")
            return {"CANCELLED"}
        jd, lst, placed = generate_starmap(st)
        stars_total = st.num_stars
        self.report({"INFO"}, f"StarMap: {len(placed)}/{stars_total} stars placed (LST {lst:.1f} deg, JD {jd:.3f})")
        return {"FINISHED"}


class STARMAP_OT_clear(bpy.types.Operator):
    bl_idname = "starmap.clear"
    bl_label = "Clear StarMap"
    bl_description = "Remove generated StarMap collection"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        clear_starmap()
        self.report({"INFO"}, "StarMap cleared")
        return {"FINISHED"}


class STARMAP_OT_use_now(bpy.types.Operator):
    bl_idname = "starmap.use_now"
    bl_label = "Use current UTC"
    bl_description = "Set date/time to current UTC"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        st = context.scene.starmap_settings
        now = datetime.now(timezone.utc)
        st.year, st.month, st.day = now.year, now.month, now.day
        st.hour, st.minute = now.hour, now.minute
        return {"FINISHED"}


class STARMAP_OT_setup_camera(bpy.types.Operator):
    bl_idname = "starmap.setup_camera"
    bl_label = "Setup lat/long camera"
    bl_description = "Create/select equirectangular panoramic camera at origin for 2:1 lat/long renders"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        cam_data = bpy.data.cameras.get("StarMap_Equirect")
        if cam_data is None:
            cam_data = bpy.data.cameras.new("StarMap_Equirect")
        cam_data.type = "PANO"
        try:
            cam_data.panorama_type = "EQUIRECTANGULAR"
        except Exception:
            pass
        ob = bpy.data.objects.get("StarMap_Equirect")
        if ob is None:
            ob = bpy.data.objects.new("StarMap_Equirect", cam_data)
            scene.collection.objects.link(ob)
        ob.location = (0.0, 0.0, 0.0)
        # Face true north (+Y). Verified by render calibration: with
        # North=+Y/East=+X/Up=+Z, rotation (90,0,0) gives a correct-handed
        # panorama: U = az/360 + 0.5 (centre = north, seam = south),
        # V = (alt+90)/180. East appears right-of-centre, as seen facing north.
        ob.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        # stars sit at sphere_radius: default far-clip (1000) would clip them away
        try:
            st = context.scene.starmap_settings
            rad = float(st.sphere_radius)
        except Exception:
            rad = 1000.0
        cam_data.clip_start = max(0.01, min(0.1, rad * 0.001))
        cam_data.clip_end = rad * 10.0 + 1000.0
        scene.camera = ob
        scene.render.resolution_x = 2048
        scene.render.resolution_y = 1024
        scene.render.resolution_percentage = 100
        # black sky: ensure world background is near-black
        ensure_black_world()
        self.report({"INFO"}, "Equirect camera ready: render (F12) gives 2:1 lat/long. Centre U=0.5 is NORTH, seam (U=0/1) is south.")
        return {"FINISHED"}


class STARMAP_OT_make_2d(bpy.types.Operator):
    bl_idname = "starmap.make_2d"
    bl_label = "Make 2D lat/long image"
    bl_description = "Direct mathematical equirectangular render (no Cycles needed). U = az/360+0.5 (0.5=north), V = (alt+90)/180"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        st = context.scene.starmap_settings
        stars = load_stars(st.num_stars)
        jd, lst, placed = compute_sky(st, stars)
        W = int(st.image_width)
        H = W // 2
        try:
            import numpy as np
            use_np = True
        except ImportError:
            use_np = False

        if use_np:
            import numpy as np
            img_arr = np.zeros((H, W, 4), dtype=np.float32)
            img_arr[:, :, 3] = 1.0
            # faint graticule: horizon + cardinals.
            # U convention matches the 3D camera: U = az/360 + 0.5 (0.5=N).
            img_arr[H // 2, :, 0:3] = 0.18
            for az in (0.0, 90.0, 180.0, 270.0):
                img_arr[:, int((az / 360.0 + 0.5) % 1.0 * W) % W, 0:3] = 0.12

            def splat(u, v, rgb, peak, sigma):
                cx = u * W
                cy = v * H
                r = int(math.ceil(sigma * 3.0)) + 1
                x0 = max(0, int(cx) - r)
                x1 = min(W - 1, int(cx) + r)
                y0 = max(0, int(cy) - r)
                y1 = min(H - 1, int(cy) + r)
                for yy in range(y0, y1 + 1):
                    # wrap x for seam at north meridian
                    for xx in range(x0, x1 + 1):
                        dx = min(abs(xx - cx), W - abs(xx - cx))
                        dy = yy - cy
                        g = math.exp(-(dx * dx + dy * dy) / (2.0 * sigma * sigma))
                        val = peak * g
                        # NOTE: image rows are bottom-up in Blender; numpy row 0 = bottom here
                        # so that foreach_set ordering matches: we fill then flip below.
                        for c in range(3):
                            img_arr[yy, xx % W, c] += val * rgb[c]

            for p in placed:
                s = p["star"]
                u = (p["az"] / 360.0 + 0.5) % 1.0
                v = (p["alt"] + 90.0) / 180.0
                rgb = bv_to_linear_rgb(s["bv"]) if st.color_by_temp else (1.0, 1.0, 1.0)
                # compressed photographic scaling so faint stars stay visible
                peak = math.pow(10.0, -0.2 * (s["mag"] + 1.5))
                peak = max(0.03, min(3.5, peak)) * 1.2
                sigma = max(0.8, min(4.5, 1.1 * math.pow(10.0, -0.12 * s["mag"]) + 0.6))
                splat(u, v, rgb, peak, sigma)
            # sun marker
            if st.show_sun:
                ra_sun, dec_sun = sun_radec_approx(jd)
                alt, az = equatorial_to_horizontal(ra_sun, dec_sun, st.latitude, lst)
                if not (st.hide_below_horizon and alt < 0.0):
                    splat((az / 360.0 + 0.5) % 1.0, (alt + 90.0) / 180.0, (1.0, 0.8, 0.55), 3.0, 5.0)
            img_arr[:, :, 0:3] = np.clip(img_arr[:, :, 0:3], 0.0, 1.0)
            # Blender Image.pixels expects rows bottom-to-top; our array row 0 is already bottom (v=0)
            flat = img_arr.reshape(-1).tolist()
            img = bpy.data.images.get("StarMap_Equirect")
            if img is None or img.size[0] != W or img.size[1] != H:
                if img is not None:
                    bpy.data.images.remove(img)
                img = bpy.data.images.new("StarMap_Equirect", W, H, float_buffer=True)
            img.pixels.foreach_set(flat)
            img.update()
        else:
            # pure-python fallback (slower)
            pixels = [0.0] * (W * H * 4)
            for i in range(W * H):
                pixels[i * 4 + 3] = 1.0
            # horizon line
            hy = H // 2
            for x in range(W):
                for c in range(3):
                    pixels[(hy * W + x) * 4 + c] = 0.18

            def splat(u, v, rgb, peak, sigma):
                cx = u * W
                cy = v * H
                r = int(math.ceil(sigma * 3.0)) + 1
                for yy in range(max(0, int(cy) - r), min(H - 1, int(cy) + r) + 1):
                    for xx in range(int(cx) - r, int(cx) + r + 1):
                        xxx = xx % W
                        dx = min(abs(xx - cx), W - abs(xx - cx))
                        dy = yy - cy
                        g = math.exp(-(dx * dx + dy * dy) / (2.0 * sigma * sigma))
                        idx = (yy * W + xxx) * 4
                        for c in range(3):
                            pixels[idx + c] += peak * g * rgb[c]

            for p in placed:
                s = p["star"]
                u = (p["az"] / 360.0 + 0.5) % 1.0
                v = (p["alt"] + 90.0) / 180.0
                rgb = bv_to_linear_rgb(s["bv"]) if st.color_by_temp else (1.0, 1.0, 1.0)
                peak = max(0.03, min(3.5, math.pow(10.0, -0.2 * (s["mag"] + 1.5)))) * 1.2
                sigma = max(0.8, min(4.5, 1.1 * math.pow(10.0, -0.12 * s["mag"]) + 0.6))
                splat(u, v, rgb, peak, sigma)
            # clip
            for i in range(W * H):
                for c in range(3):
                    k = i * 4 + c
                    if pixels[k] > 1.0:
                        pixels[k] = 1.0
            img = bpy.data.images.get("StarMap_Equirect")
            if img is None or list(img.size) != [W, H]:
                if img is not None:
                    bpy.data.images.remove(img)
                img = bpy.data.images.new("StarMap_Equirect", W, H, float_buffer=True)
            img.pixels.foreach_set(pixels)
            img.update()

        self.report({"INFO"}, f"2D lat/long image 'StarMap_Equirect' ({W}x{H}, {len(placed)} stars). See Image Editor.")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

class STARMAP_PT_panel(bpy.types.Panel):
    bl_label = "StarMap"
    bl_idname = "STARMAP_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "StarMap"

    def draw(self, context):
        st = context.scene.starmap_settings
        L = self.layout
        L.label(text="Observer (planetarium-accurate)")
        L.prop(st, "city_preset")
        r = L.row(align=True)
        r.prop(st, "latitude")
        r.prop(st, "longitude")
        L.label(text="Date / time (UTC)")
        r = L.row(align=True)
        r.prop(st, "year")
        r.prop(st, "month")
        r.prop(st, "day")
        r = L.row(align=True)
        r.prop(st, "hour")
        r.prop(st, "minute")
        L.operator("starmap.use_now", icon="TIME")
        L.separator()
        L.label(text="Sky")
        L.prop(st, "num_stars")
        L.prop(st, "sphere_radius")
        L.prop(st, "placement_mode")
        if st.placement_mode == "TRUE":
            L.prop(st, "distance_scale")
        L.prop(st, "hide_below_horizon")
        L.prop(st, "show_sun")
        L.separator()
        L.label(text="Cubes (size ~ magnitude)")
        L.prop(st, "base_size")
        L.prop(st, "size_by_mag")
        L.prop(st, "base_emission")
        L.prop(st, "brightness_by_mag")
        L.prop(st, "color_by_temp")
        L.separator()
        L.label(text="Helpers")
        L.prop(st, "show_cardinals")
        L.prop(st, "label_brightest")
        L.separator()
        L.operator("starmap.generate", icon="LIGHT_SUN")
        L.operator("starmap.clear", icon="TRASH")
        L.separator()
        L.label(text="Lat/long output (needs clear view:")
        L.label(text="hide/unhide other objects)")
        L.operator("starmap.setup_camera", icon="CAMERA_DATA")
        L.prop(st, "image_width")
        L.operator("starmap.make_2d", icon="IMAGE_DATA")
        L.label(text="Render F12 = lat/long. Or use 2D image.")


classes = (
    StarMapSettings,
    STARMAP_OT_generate,
    STARMAP_OT_clear,
    STARMAP_OT_use_now,
    STARMAP_OT_setup_camera,
    STARMAP_OT_make_2d,
    STARMAP_PT_panel,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.starmap_settings = bpy.props.PointerProperty(type=StarMapSettings)


def unregister():
    try:
        del bpy.types.Scene.starmap_settings
    except Exception:
        pass
    for c in reversed(classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass


if __name__ == "__main__":
    register()
