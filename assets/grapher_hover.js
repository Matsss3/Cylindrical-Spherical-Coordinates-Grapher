(function (root) {
    'use strict';

    const CLEAR_DELAY_MS = 120;

    function lazy(globalName, file) {
        if (root[globalName]) return root[globalName];
        if (typeof require === 'function') return require(file);
        throw new Error(globalName + 'is not loaded; check script order in assets/.');
    }
    function coords() { return lazy('GrapherCoords', './grapher_coords.js'); }
    function construction() { return lazy('GrapherConstruction', './grapher_construction.js'); }

    function firstPoint(ev) {
        return ev && ev.points && ev.points.length ? ev.points[0] : null;
    }

    function mathTrace(gd, pt) {
        let fd = pt.fullData;
        if (!fd || !fd.meta) {
            const all = gd._fullData;
            fd = all && all[pt.curveNumber];
        }
        const meta = fd && fd.meta && fd.meta.grapher;
        if (!meta || meta.role !== 'math') return null;
        return { meta: meta, fullData: fd };
    }

    function create(gd, backend, opts) {
        const options = opts || {};
        const st = {
            active: false,
            bound: false,
            lastKey: null,
            timer: 0,
            dragging: false,
            leftWhileDragging: false,
            hovers: 0,
            errors: 0,
        };
        let lastState = null;

        function notify(state, con) {
            lastState = state;
            if (typeof options.onChange === 'function') {
                try {
                    options.onChange(state, con);
                } catch (err) {
                    console.log("TODO ERROR");
                    // TODO
                }
            }
        }

        function cancelTimer() {
            if (st.timer) {
                clearTimeout(st.timer);
                st.timer = 0;
            }
        }

        function clear() {
            cancelTimer();
            const had = st.lastKey !== null || lastState !== null;
            st.lastKey = null;
            backend.clear();
            if (had) notify(null, null);
        }

        function onHover(ev) {
            if (!st.active) return;
            try {
                const pt = firstPoint(ev);
                if (!pt) return;
                const found = mathTrace(gd, pt);
                if (!found) return;
                cancelTimer();

                const meta = found.meta;
                const key = String(meta.objectId) + '|' + String(pt.pointNumber);
                if (key === st.lastKey) return;

                const state = coords().resolveState(
                    meta,
                    pt.pointNumber,
                    found.fullData.customdata,
                    { x: pt.x, y: pt.y, z: pt.z },
                    { objectId: meta.objectId, name: meta.name }
                );
                const con = state ? construction().buildConstruction(state) : null;

                if (!con) {
                    st.lastKey = null;
                    backend.clear();
                    notify(null, null);
                    return;
                }
                if (!backend.setConstruction(con)) return;
                st.lastKey = key;
                st.hovers += 1;
                notify(state, con);
            } catch (err) {
                st.errors += 1;
                if (st.errors === 1 && typeof console !== 'undefined') {
                    console.warn('[grapher] hover handler error: ', err)
                }
            }
        }

        function onUnhover() {
            if (!st.active || st.dragging) return;
            cancelTimer();
            st.timer = setTimeout(function () {
                st.timer = 0;
                clear();
            }, CLEAR_DELAY_MS);
        }

        function onPointerDown() {
            st.dragging = true;
            st.leftWhileDragging = false;
        }

        function onPointerUp() {
            if (!st.dragging) return;
            st.dragging = false;
            if (st.leftWhileDragging) {
                st.leftWhileDragging = false;
                if (st.active) clear();
            }
        }

        function onMouseLeave() {
            if (!st.active) return;
            if (st.dragging) st.leftWhileDragging = true;
            else clear();
        }

        function bind() {
            if (st.bound) return;
            gd.on('plotly_hover', onHover);
            gd.on('plotly_click', onHover);
            gd.on('plotly_unhover', onUnhover);
            gd.addEventListener('pointerdown', onPointerDown, true);
            gd.addEventListener('mouseleave', onMouseLeave);
            root.addEventListener('pointerup', onPointerUp, true);
            root.addEventListener('pointercancel', onPointerUp, true);
            st.bound = true;
        }

        function unbind() {
            if (!st.bound) return;
            if (typeof gd.removeListener === 'function') {
                gd.removeListener('plotly_hover', onHover);
                gd.removeListener('plotly_click', onHover);
                gd.removeListener('plotly_unhover', onUnhover);
            }
            gd.removeEventListener('pointerdown', onPointerDown, true);
            gd.removeEventListener('mouseleave', onMouseLeave);
            root.removeEventListener('pointerup', onPointerUp, true);
            root.removeEventListener('pointercancel', onPointerUp, true);
            st.bound = false;
        }

        function setActive(on) {
            st.active = !!on;
            if (!st.active) {
                st.dragging = false;
                st.leftWhileDragging = false;
                clear();
            }
        }

        function reset() {
            st.dragging = false;
            st.leftWhileDragging = false;
            clear();
        }

        return {
          bind: bind,
          unbind: unbind,
          setActive: setActive,
          reset: reset,
          clear: clear,
          stats: st,
          lastState: function () { return lastState; },
        };
    }

    const api = { CLEAR_DELAY_MS: CLEAR_DELAY_MS, create: create };

    if (typeof module === 'object' && module && module.exports) {
        module.exports = api;
    } else {
        root.GrapherHover = api;
    }
})(typeof globalThis !== 'undefined' ? globalThis : this);
