/*
 * Per coordinate system: state -> drawing primitives.
 * The SVG backend projects the points and styles the primitives.
 *
 * Returned arrays are fresh copies; the caller may mutate them.
 */
(function (root) {
    'use strict';

    function lazy(globalName, file) {
        if (root[globalName]) return root[globalName];
        if (typeof require === 'function') return require(file);
        throw new Error(globalName + ' is not loaded: check script order in assets/.');
    }
    function coords() { return lazy('GrapherCoords', './grapher_coords.js'); }
    function format() { return lazy('GrapherFormat', './grapher_format.js'); }

    const TUNING = {
        arcStep: Math.PI / 24,
        thetaArc: { frac: 0.5, min: 0.4, max: 2.0 }, // radius = clamp(frac * |OQ|, min, max)
        phiArc: { frac: 0.35, min: 0.5, max: 2.0 }, // radius = clamp(frac * |OQ|, min, max)
        labelScale: 1.3,
        rightAngle: { size: 0.25, frac: 0.35, minLen: 0.05 },
        circleOpacity: 0.35,
        guideOpacity: 0.8,
        labelOffsetPx: {
            rho: [0, -10],
            r: [0, 10],
            x: [0, 10],
            y: [0, 10],
            z: [0, 10],
            theta: [0, 0],
            varphi: [0, 0],
        },
    };

    function clamp(value, lo, hi) {
        return Math.min(hi, Math.max(lo, value));
    }

    function offsetFor(coord) {
        const o = TUNING.labelOffsetPx[coord];
        return o ? o.slice() : [0, 0];
    }

    function newScene() {
        return { paths: [], labels: [] };
    }

    function pushPolyLine(scene, id, kind, colorKey, points, extra) {
        scene.paths.push(Object.assign({
            id: id,
            kind: kind,
            colorKey: colorKey,
            dashed: false,
            opacity: 1,
            points: points.map(function (p) { return p.slice(); }),
        }, extra || {}));
    }

    /** Straight segment; dropped (returns false) if shorter than the singularity threshold. */
    function pushLine(scene, id, kind, colorKey, a, b, extra) {
        const C = coords();
        if (C.vec.dist(a, b) < C.SING_EPS) return false;
        pushPolyLine(scene, id, kind, colorKey, [a, b], extra);
        return true;
    }

    function pushGuide(scene, id, a, b, extra) {
        return pushLine(scene, id, 'guide', 'guide', a, b,
            Object.assign({ dashed: true, opacity: TUNING.guideOpacity }, extra || {}));
    }

    function pushLabel(scene, coord, value, anchor) {
        scene.labels.push({
            id: coord,
            colorKey: coord,
            text: format().fmtCoord(coord, value),
            anchor: anchor.slice(),
            offsetPx: offsetFor(coord),
        });
    }

    /** Small square corner at `corner`, between the directions towards `a` and `b`. */
    function pushRightAngle(scene, corner, a, b) {
        const V = coords().vec;
        const T = TUNING.rightAngle;
        const la = V.dist(corner, a);
        const lb = V.dist(corner, b);
        if (la < T.minLen || lb < T.minLen) return;
        const size = Math.min(T.size, T.frac * la, T.frac * lb);
        const u = V.scale(V.unit(V.sub(a, corner)), size);
        const v = V.scale(V.unit(V.sub(b, corner)), size);
        const p1 = V.add(corner, u);
        const p3 = V.add(corner, v);
        const p2 = V.add(p1, v);
        pushPolyLine(scene, 'marker-right-angle', 'marker', 'guide', [p1, p2, p3],
            { opacity: TUNING.guideOpacity });
    }

    /**
    * Azimuth arc + label, shared by spherical and cylindrical. 
    * Only called when theta is defined.
    */
    function pushThetaArc(scene, native, radial) {
        const C = coords();
        const R = clamp(TUNING.thetaArc.frac * radial, TUNING.thetaArc.min, TUNING.thetaArc.max);
        const angle = native.theta;
        if (R * angle >= C.SING_EPS) {
            pushPolyLine(scene, 'theta-arc', 'arc', 'theta', C.arcXY(R, angle, TUNING.arcStep));
        }
        const R1 = TUNING.labelScale * R;
        pushLabel(scene, 'theta', angle,
            [R1 * Math.cos(angle / 2), R1 * Math.sin(angle / 2), 0]);
    }

    function buildSpherical(scene, st) {
        const C = coords();
        const V = C.vec;
        const n = st.native;
        const c = st.cartesian;
        const O = [0, 0, 0];
        const P = [c.x, c.y, c.z];
        const Q = [c.x, c.y, 0];

        if (st.singular.origin) {
            pushLabel(scene, 'rho', n.rho, P);
            return;
        }

        pushGuide(scene, 'guide-oq', O, Q);
        pushGuide(scene, 'guide-qp', Q, P);
        pushRightAngle(scene, Q, O, P);

        if (st.defined.theta) pushThetaArc(scene, n, st.geometry.radial);

        // varphi arc: vertical plane through OP, from +z to OP. 
        // The zero-length arc at varphi = 0 is dropped but its label is kept.
        if (st.defined.varphi) {
            const R = clamp(TUNING.phiArc.frac * st.geometry.distance,
                TUNING.phiArc.min, TUNING.phiArc.max);
            if (R * n.varphi >= C.SING_EPS) {
                pushPolyLine(scene, 'varphi-arc', 'arc', 'varphi',
                    C.arcVertical(R, n.theta, n.varphi, TUNING.arcStep));
            }
            const R1 = TUNING.labelScale * R;
            const half = n.varphi / 2;
            pushLabel(scene, 'varphi', n.varphi, [
                R1 * Math.sin(half) * Math.cos(n.theta),
                R1 * Math.sin(half) * Math.sin(n.theta),
                R1 * Math.cos(half),
            ]);
        }

        pushLine(scene, 'rho', 'line', 'rho', O, P);
        pushLabel(scene, 'rho', n.rho, V.mid(O, P));
    }

    function buildCylindrical(scene, st, opts) {
        const C = coords();
        const V = C.vec;
        const n = st.native;
        const c = st.cartesian;
        const O = [0, 0, 0];
        const P = [c.x, c.y, c.z];
        const Q = [c.x, c.y, 0];
        
        if (opts.circle && st.defined.theta) {
            pushPolyLine(scene, 'guide-circle', 'circle', 'guide',
                C.circleXY(st.geometry.radial, 0, Math.PI / 32),
                { opacity: TUNING.circleOpacity });
        }
        pushRightAngle(scene, Q, O, P);

        if (st.defined.theta) pushThetaArc(scene, n, st.geometry.radial);

        pushLine(scene, 'r', 'line', 'r', O, Q);
        pushLine(scene, 'z', 'line', 'z', Q, P);

        pushLabel(scene, 'r', n.r, V.mid(O, Q));
        pushLabel(scene, 'z', n.z, V.mid(Q, P));
    }

    function buildCartesian(scene, st, opts) {
        const V = coords().vec;
        const x = st.native.x;
        const y = st.native.y;
        const z = st.native.z;

        const O = [0, 0, 0];
        const P = [x, y, z];
        const X = [x, 0, 0];
        const Y = [0, y, 0];
        const Z = [0, 0, z];
        const Pxy = [x, y, 0];
        const Pxz = [x, 0, z];
        const Pyz = [0, y, z];

        if (opts.projections) {
            [
                ['guide-p-xz', P, Pxz],
                ['guide-p-yz', P, Pyz],
                ['guide-xy-y', Pxy, Y],
                ['guide-xz-x', Pxz, X],
                ['guide-xz-z', Pxz, Z],
                ['guide-yz-y', Pyz, Y],
                ['guide-yz-z', Pyz, Z],
            ].forEach(function (g) {
                pushGuide(this, g[0], g[1], g[2], { group: 'projection' })
            }, scene);
        }

        pushLine(scene, 'x', 'line', 'x', O, X);
        pushLine(scene, 'y', 'line', 'y', X, Pxy);
        pushLine(scene, 'z', 'line', 'z', Pxy, P);

        pushLabel(scene, 'x', x, V.mid(O, X));
        pushLabel(scene, 'y', y, V.mid(X, Pxy));
        pushLabel(scene, 'z', z, V.mid(Pxy, P));
    }


    /**
    * Build the primitives for one state.
    *
    * opts:
    *   projections  (default true)  Cartesian: dashed projection guides (6.4)
    *   circle       (default true)  cylindrical: faint circle of radius r at z = 0 (6.3)
    *
    */
    function buildConstruction(state, opts) {
        if (!state) return null;
        const o = Object.assign({ projections: true, circle: true }, opts || {});
        const scene = newScene();

        switch (state.system) {
            case 'spherical':
                buildSpherical(scene, state);
                break;
            case 'cylindrical':
                buildCylindrical(scene, state, o);
                break;
            case 'cartesian':
                buildCartesian(scene, state, o);
                break;
            default:
                throw new Error('Unknown coordinate system: ' + String(state.system));
        }

        const c = state.cartesian;
        return {
            system: state.system,
            point: [c.x, c.y, c.z],
            paths: scene.paths,
            labels: scene.labels,
            defined: Object.assign({}, state.defined),
        };
    }

    const api = {
        TUNING: TUNING,
        buildConstruction: buildConstruction,
    };

    if (typeof module === 'object' && module && module.exports) {
        module.exports = api;
    } else {
        root.GrapherConstruction = api;
    }
})(typeof globalThis !== 'undefined' ? globalThis : this);
