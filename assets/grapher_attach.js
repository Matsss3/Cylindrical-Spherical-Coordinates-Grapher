/*
 * Entry point of the interaction layer: binds it to one Plotly graph div + on/off toggle.
 *
 *   attach(gd)            -> { ok, reason? }   idempotent (gd.__grapherBound)
 *   setActive(gd, on)     -> { ok, reason? }   the toggle
 *   isActive(gd)          -> boolean
 *   whenReady(id, fn)     calls fn(gd) once the graph's 3D scene exists (rAF retry)
 *   findGraph(id)         -> graph div or null
 *   get(gd)               -> internal instance (backend, hover, ...) for tests
 *
 * Off (default): nothing is installed beyond inert event handlers, the tooltip
 * and the axis spikes are exactly Plotly's. On: the tooltip is hidden with the
 * CSS class `grapher-hover-on`, spikes are switched off with one relayout, 
 * the overlay and hover handler are active.
 */
(function (root) {
    'use strict';

    const ACTIVE_CLASS = 'grapher-hover-on';
    const SPIKE_KEYS = ['x', 'y', 'z'];

    const MSG = {
        noPlotly: 'No se encontró Plotly en la aplicación. Coordenadas desactivadas.',
        noMeta: 'La figura no incluye los datos de coordenadas. Función desactivada.',
        version: function (expected, actual) {
            return `La versión de Plotly (${actual}) no coincide con la adecuada (${expected}). Función desactivada.`;
        },
        internals: 'No se pudo acceder a la escena 3D de Plotly. Función desactivada.'
    };

    function lazy(globalName, file) {
        if (root[globalName]) return root[globalName];
        if (typeof require === 'function') return require(file);
        throw new Error(globalName + 'is not loaded; check script order in assets/.');
    }
    function backendModule() { return lazy('GrapherBackendSvg', ''); }
    function hoverModule() { return lazy('GrapherHover', ''); }

    function findGraph(graphId) {
        const host = document.getElementById(graphId);
        if (!host) return null;
        return host.classList.contains('js-plotly-plot') ? host : host.querySelector('.js-plotly-plot');
    }

    function sceneReady(gd) {
        const fl = gd && gd._fullLayout;
        return !!(fl && fl.scene && fl.scene._scene && fl.scene._scene.glplot);
    }

    /** Call fn(gd) as soon as the graph and its 3D scene exist (rAF polling). */
    function whenReady(graphId, fn, opts) {
        const maxFrames = (opts && opts.frames) || 600;
        let frames = 0;
        (function tick() {
            const gd = findGraph(graphId);
            if (gd && sceneReady(gd)) {
                fn(gd);
                return;
            }
            frames += 1;
            if (frames <= maxFrames) requestAnimationFrame(tick);
        })();
    }

    function checkSupport(gd) {
        const Plotly = root.Plotly;
        if (!Plotly || typeof gd.on !== 'function') return { ok: false, reason: MSG.noPlotly };
        const layoutMeta = gd._fullLayout && gd._fullLayout.meta;
        const g = layoutMeta && layoutMeta.grapher;
        if (!g || !g.plotly) {
            console.log(MSG.noMeta + ' 0');
            return { ok: false, reason: MSG.noMeta };
        }
        if (String(Plotly.version) !== String(g.plotly)) return { ok: false, reason: MSG.version(g.plotly, Plotly.version) };
        return { ok: true };
    }

    function currentSpikes(gd) {
        const scene = gd._fullLayout && gd._fullLayout.scene;
        const out = {};
        SPIKE_KEYS.forEach(function (k) {
            const ax = scene && scene[k + 'axis'];
            out[k] = !!(ax && ax.showspikes);
        });
        return out;
    }

    function spikesOff(inst) {
        const gd = inst.gd;
        const now = currentSpikes(gd);
        if (!inst.savedSpikes) inst.savedSpikes = now;
        const upd = {};
        SPIKE_KEYS.forEach(function (k) {
            if (now[k]) upd['scene.' + k + 'axis.showspikes'] = false;
        });
        if (Object.keys(upd).length) root.Plotly.relayout(gd, upd);
    }

    function spikesRestore(inst) {
        const saved = inst.savedSpikes;
        inst.savedSpikes = null;
        if (!saved) return;
        const now = currentSpikes(inst.gd);
        const upd = {};
        SPIKE_KEYS.forEach(function (k) {
            if (saved[k] !== now[k]) upd['scene.' + k + 'axis.showspikes'] = saved[k];
        });
        if (Object.keys(upd).length) root.Plotly.relayout(inst.gd, upd);
    }

    function onReact(inst) {
        inst.hover.reset();
        inst.backend.reset();
        if (inst.active) {
            inst.gd.classList.add(ACTIVE_CLASS);
            inst.backend.ensure();
            spikesOff(inst);
        }
    }

    function attach(gd) {
        if (!gd) return { ok: false, reason: MSG.noPlotly };
        if (gd.__grapherBound) return { ok: true };

        const support = checkSupport(gd);
        if (!support.ok) return support;

        const inst = {
            gd: gd,
            active: false,
            savedSpikes: null,
            backend: null,
            hover: null,
        };
        inst.backend = backendModule().create(gd);
        inst.hover = hoverModule().create(gd, inst.backend);
        inst.hover.bind();
        gd.on('plotly_react', function () { onReact(inst); });

        gd.__grapher = inst;
        gd.__grapherBound = true;
        return { ok: true };
    }

    function setActive(gd, on) {
        if (!gd) return { ok: false, reason: MSG.noPlotly };
        const att = attach(gd);
        if (!att.ok) return att;
        const inst = gd.__grapher;

        if (on) {
            const ens = inst.backend.ensure();
            if (!ens.ok) return { ok: false, reason: MSG.internals, detail: ens.reason };
            inst.active = true;
            inst.backend.setActive(true);
            inst.hover.setActive(true);
            gd.classList.add(ACTIVE_CLASS);
            spikesOff(inst);
        } else {
            inst.active = false;
            inst.hover.setActive(false);
            inst.backend.setActive(false);
            gd.classList.remove(ACTIVE_CLASS);
            spikesRestore(inst);
        }
        return { ok: true };
    }

    function isActive(gd) {
        return !!(gd && gd.__grapher && gd.__grapher.active);
    }

    function get(gd) {
        return gd && gd.__grapher ? gd.__grapher : null;
    }

    const api = {
        ACTIVE_CLASS: ACTIVE_CLASS,
        MESSAGES: MSG,
        findGraph: findGraph,
        whenReady: whenReady,
        attach: attach,
        setActive: setActive,
        isActive: isActive,
        get: get,
    };

    if (typeof module === 'object' && module && module.exports) {
        module.exports = api;
    } else {
        root.GrapherInteraction = api;
    }
})(typeof globalThis !== 'undefined' ? globalThis : this);
