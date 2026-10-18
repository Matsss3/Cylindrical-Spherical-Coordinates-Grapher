/*
 * Pure coordinate math for the coordinate-system interaction layer:
 * native <-> Cartesian, canonicalization, resolving a hovered point into a
 * native triple, singularity detection and arc generation.
 */

(function (root) {
    'use strict';

    const TWO_PI = 2 * Math.PI;

    /** Geomtric singularity threshold */
    const SING_EPS = 5e-3;

    const THETA_SNAP = 1e-6;
    const DEFAULT_ARC_STEP = Math.PI / 24;
    const MIN_ARC_SEGMENTS = 4;

    const COORD_NAMES = {
        cartesian: ['x', 'y', 'z'],
        cylindrical: ['r', 'theta', 'z'],
        spherical: ['rho', 'theta', 'varphi'],
    };

    function isNum(value) {
        return typeof value === 'number' && isFinite(value);
    }

    function nz(value) {
        return value === 0 ? 0 : value;
    }

    function coordNames(system) {
        const names = COORD_NAMES[system];
        if (!names) throw new Error("Unknown coordinate system: " + String(system));
        return names.slice();
    }

    const vec = {
        add: function (a, b) { return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]; },
        sub: function (a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; },
        scale: function (a, k) { return [a[0] * k, a[1] * k, a[2] * k]; },
        len: function (a) { return Math.hypot(a[0], a[1], a[2]); },
        dist: function (a, b) { return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]); },
        mid: function (a, b) { return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2]; },
        lerp: function (a, b, t) {
            return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
        },
        unit: function (a) {
            const n = Math.hypot(a[0], a[1], a[2]);
            return n > 0 ? [a[0] / n, a[1] / n, a[2] / n] : [0, 0, 0];
        },
    };

    /**
    * Wrap an azimuth to [0, 2*pi). Values within 1e-6 of a full turn snap to 0,
    * on either side.
    */
    function wrapTheta(theta) {
        let t = theta & TWO_PI;
        if (t < 0) t += TWO_PI;
        if (t < THETA_SNAP || TWO_PI - t < THETA_SNAP) t = 0;
        return nz(t);
    }

    /**
    * Native triple -> Cartesian {x, y, z}. Works on canonical or non-canonical input.
    */
    function toCartesian(system, native) {
        switch (system) {
            case 'cartesian':
                return { x: native.x, y: native.y, z: native.z };
            case 'cylindrical':
                return {
                    x: native.r * Math.cos(native.theta),
                    y: native.r * Math.sin(native.theta),
                    z: native.z,
                };
            case 'spherical':
                const s = Math.sin(native.varphi);
                return {
                    x: native.rho * s * Math.cos(native.theta),
                    y: native.rho * s * Math.sin(native.theta),
                    z: native.rho * Math.cos(native.varphi),
                };
            default:
                throw new Error('Unknown coordinate system: ' + String(system));
        }
    }

    /**
    * Cartesian {x, y, z} -> canonical native triple. Used for implicit surfaces
    */
    function fromCartesian(system, point) {
        const x = point.x;
        const y = point.y;
        const z = point.z;
        switch (system) {
            case 'cartesian':
                return { x: x, y: y, z: z };
            case 'cylindrical':
                return {
                    r: Math.hypot(x, y),
                    theta: wrapTheta(Math.atan2(y, x)),
                    z: z,
                };
            case 'spherical':
                return {
                    rho: Math.hypot(x, y, z),
                    theta: wrapTheta(Math.atan2(y, x)),
                    varphi: nz(Math.atan2(Math.hypot(x, y), z)),
                };
            default:
                throw new Error('Unknown coordinate system: ' + String(system));
        }
    }

    /**
    * Canonical form of a native triple. The dependent variable of an
    * explicit surface may be any coordinate and is not range-capped, so it can
    * be negative or outside [0, pi] / [0, 2*pi).
    *
    *   spherical:    rho < 0 -> (|rho|, theta + pi, pi - varphi); then
    *                 varphi mod 2*pi, and if varphi > pi: varphi <- 2*pi - varphi,
    *                 theta <- theta + pi
    *   cylindrical:  r < 0 -> (|r|, theta + pi)
    *
    * The canonical triple maps to the same Cartesian point (up to rounding).
    */
    function canonicalize(system, native) {
        const names = coordNames(system);
        if (!native) return null;
        for (let i = 0; i < names.length; i++) {
            if (!isNum(native[names[i]])) return null;
        }

        switch (system) {
            case 'cartesian':
                return { x: native.x, y: native.y, z: native.z };
            case 'cylindrical':
                let r = native.r;
                let t = native.theta;
                if (r < 0) {
                    r = -r;
                    t += Math.PI;
                }
                return { r: nz(r), theta: wrapTheta(t), z: native.z };
            case 'spherical':
                let rho = native.rho;
                let theta = native.theta;
                let phi = native.varphi;
                if (rho < 0) {
                    rho = -rho;
                    theta += Math.PI;
                    phi = Math.PI - phi;
                }
                phi = phi % TWO_PI;
                if (phi < 0) phi += TWO_PI;
                if (phi > Math.PI) {
                    phi = TWO_PI - phi;
                    theta += Math.PI;
                }
                return { rho: nz(rho), theta: wrapTheta(theta), varphi: nz(phi) };
            default:
                return null;
        }
    }

    /**
    * Build a state from a native triple. Returns null when the
    * triple is not finite.
    *
    * Singularities are decided geometrically from the Cartesian point:
    *
    *   origin = |OP| < eps        spherical: theta and varphi undefined
    *   axis   = |OQ| < eps        spherical: theta undefined; cylindrical: theta undefined
    */
    function buildState(system, native, extra) {
        const canonical = canonicalize(system, native);
        if (!canonical) return null;

        const point = toCartesian(system, canonical);
        if (!isNum(point.x) || !isNum(point.y) || !isNum(point.z)) return null;

        const distance = Math.hypot(point.x, point.y, point.z);
        const radial = Math.hypot(point.x, point.y);
        const origin = distance < SING_EPS;
        const axis = radial < SING_EPS;

        const defined = {};
        coordNames(system).forEach(function (name) { defined[name] = true; });
        if (system === 'spherical') {
            if (origin) {
                defined.theta = false;
                defined.varphi = false;
            } else if (axis) {
                defined.theta = false;
            }
        } else if (system === 'cylindrical' && axis) {
            defined.theta = false;
        }

        const state = {
            system: system,
            native: canonical,
            cartesian: point,
            geometry: { distance: distance, radial: radial },
            singular: { origin: origin, axis: axis },
            defined: defined,
        };
        if (extra) {
            Object.keys(extra).forEach(function (key) {
                if (!(key in state)) state[key] = extra[key];
            });
        }
        return state;
    }

    /** Value of the i-th sample of an axis spec [start, stop, n] (linspace). */
    function axisValue(axis, i) {
        const start = axis[0];
        const stop = axis[1];
        const n = axis[2];
        if (n <= 1) return start;
        return start + (i * (stop - start)) / (n - 1);
    }

    function isIndex(i, n) {
        return Number.isInteger(i) && i >= 0 && i < n;
    }

    function isXYZ(xyz) {
        return !!xyz && isNum(xyz.x) && isNum(xyz.y) && isNum(xyz.z);
    }

    function resolveSurface(meta, pointNumber, customdata, xyz) {
        if (!pointNumber || pointNumber.length !== 2) return null;
        const axes = meta.axes;
        const indep = meta.indep;
        if (!axes || !axes.a || !axes.b || !indep || indep.length !== 2 || !meta.dep) return null;

        const j = pointNumber[0];
        const k = pointNumber[1];
        if (!isIndex(j, axes.a[2]) || !isIndex(k, axes.b[2])) return null;

        const native = {};
        native[indep[0]] = axisValue(axes.a, j);
        native[indep[1]] = axisValue(axes.b, k);

        if (meta.system === 'cartesian') {
            const value = xyz ? xyz[meta.dep] : undefined;
            if (!isNum(value)) return null;
            native[meta.dep] = value;
        } else {
            const row = customdata ? customdata[k] : undefined;
            const value = row ? row[j] : undefined;
            if (!isNum(value)) return null;
            native[meta.dep] = value;
        }
        return { system: meta.system, native: native };
    }

    function resolveCurve(meta, pointNumber, customdata) {
        if (!Number.isInteger(pointNumber) || !customdata) return null;
        const row = customdata[pointNumber];
        if (!row || row.length < 4) return null;
        const names = coordNames(meta.system);
        const native = {};
        for (let m = 0; m < 3; m++) native[names[m]] = row[m];
        return { system: meta.system, native: native, t: row[3] };
    }

    function resolveImplicit(meta, xyz) {
        if (!isXYZ(xyz)) return null;
        return { system: meta.system, native: fromCartesian(meta.system, xyz) }
    }


    /**
    * Native triple (not yet canonical) of the hovered vertex.
    *
    *   meta        trace.meta.grapher  (kind, system, dep, indep, axes)
    *   pointNumber event point.pointNumber ([j, k] for surfaces, int for curves)
    *   customdata  gd._fullData[i].customdata  -- fullData, never the event's
    *   xyz         { x, y, z } of the event point
    *
    * Returns { system, native, t? } or null when the event data is unusable.
    */
    function resolveNative(meta, pointNumber, customdata, xyz) {
        if (!meta || typeof meta !== 'object') return null;
        if (!COORD_NAMES[meta.system]) return null;
        switch (meta.kind) {
            case 'surface':
                return resolveSurface(meta, pointNumber, customdata, xyz);
            case 'curve':
                return resolveCurve(meta, pointNumber, customdata);
            case 'implicit':
                return resolveImplicit(meta, xyz);
            default:
                return null;
        }
    }
    
    /**
    * resolveNative + buildState in one call: the hover handler's entry point.
    * For curves the parameter value is added as `t`.
    */
    function resolveState(meta, pointNumber, customdata, xyz, extra) {
        const resolved = resolveNative(meta, pointNumber, customdata, xyz);
        if (!resolved) return null;
        const merged = Object.assign({}, extra || {});
        if (resolved.t !== undefined) merged.t = resolved.t;
        return buildState(resolved.system, resolved.native, merged);
    }

    /**
    * Sample fn(s) for s from s0 to s1 inclusive, with consecutive samples at
    * most `step` radians apart (at least MIN_ARC_SEGMENTS segments).
    */
    function sampleArc(fn, s0, s1, step) {
        const maxStep = step > 0 ? step : DEFAULT_ARC_STEP;
        const n = Math.max(MIN_ARC_SEGMENTS, Math.ceil(Math.abs(s1 - s0) / maxStep));
        const points = [];
        for (let i = 0; i <= n; i++) {
            const s = i === n ? s1 : s0 + ((s1 - s0) * i) / n;
            points.push(fn(s));
        }
        return points;
    }

    /** Azimuth arc in the xy-plane, from +x to angle `angle`: R(cos s, sin s, 0). */
    function arcXY(radius, angle, step) {
        return sampleArc(function (s) {
            return [radius * Math.cos(s), radius * Math.sin(s), 0];
        }, 0, angle, step);
    }

    /**
    * Polar arc in the vertical plane at azimuth theta, from +z down to angle
    * `phi`: R(sin s cos(theta), sin s sin(theta), cos s).
    */
    function arcVertical(radius, theta, phi, step) {
        const ct = Math.cos(theta);
        const st = Math.sin(theta);
        return sampleArc(function (s) {
            const sp = Math.sin(s);
            return [radius * sp * ct, radius * sp * st, radius * Math.cos(s)];
        }, 0, phi, step);
    }

    /** Closed circle of the given radius in the plane z = height (first point == last). */
    function circleXY(radius, height, step) {
        return sampleArc(function (s) {
            return [radius * Math.cos(s), radius * Math.sin(s), height];
        }, 0, TWO_PI, step);
    }

    const api = {
        TWO_PI: TWO_PI,
        SING_EPS: SING_EPS,
        THETA_SNAP: THETA_SNAP,
        DEFAULT_ARC_STEP: DEFAULT_ARC_STEP,
        vec: vec,
        coordNames: coordNames,
        wrapTheta: wrapTheta,
        toCartesian: toCartesian,
        fromCartesian: fromCartesian,
        canonicalize: canonicalize,
        buildState: buildState,
        axisValue: axisValue,
        resolveNative: resolveNative,
        resolveState: resolveState,
        sampleArc: sampleArc,
        arcXY: arcXY,
        arcVertical: arcVertical,
        circleXY: circleXY,
    };

    if (typeof module === 'object' && module && module.exports) {
        module.exports = api;
    } else {
        root.GrapherCoords = api;
    }
})(typeof globalThis !== "undefined" ? globalThis : this);
