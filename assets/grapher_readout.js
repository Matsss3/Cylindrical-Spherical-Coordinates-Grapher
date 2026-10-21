/*
 * HTML readout card shown beside the graph while "Mostrar coordenadas" is on
 *
 * Content: object name and system; the Cartesian coordinates; the native
 * coordinates (cylindrical / spherical) with each angle as `0.40pi . 1.26 rad .
 * 72deg`; `t` for curves; the active angle convention.
 */
(function (root) {
    'use strict';

    const SYSTEM_NAME = {
        cartesian: 'Cartesiano',
        cylindrical: 'Cilíndrico',
        spherical: 'Esférico',
    };

    const LATEX = {
        x: 'x', y: 'y', z: 'z', r: 'r', t: 't',
        rho: '\\rho', theta: '\\theta', varphi: '\\varphi',
    };

    const BLOCKS = {
        cartesian: [{id: 'cart', title: 'Coordenadas cartesianas', keys: ['x', 'y', 'z']}],
        cylindrical: [
            {id: 'cart', title: 'Cartesianas', keys: ['x', 'y', 'z']},
            {id: 'native', title: 'Cilíndricas', keys: ['r', 'theta', 'z']},
        ],
        spherical: [
            {id: 'cart', title: 'Cartesianas', keys: ['x', 'y', 'z']},
            {id: 'native', title: 'Esféricas', keys: ['rho', 'theta', 'varphi']},
        ],
    };

    const CONVENTION = {
        cylindrical: '\u03b8: Ángulo medido desde el eje +x',
        spherical: '\u03b8: Ángulo medido desde el eje +x \u00b7 \u03c6: Ángulo medido desde el eje +z',
    };

    const IDLE_TEXT = 'Mueva el cursor sobre un objeto para ver sus coordenadas.';

    function format() {
        if (root.GrapherFormat) return root.GrapherFormat;
        if (typeof require === 'function') return require('./grapher_format.js');
        throw new Error('GrapherFormat is not loaded: check script order in assets/');
    }

    function el(tag, cls, text) {
        const e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text !== undefined) e.textContent = text;
        return e;
    }

    function renderMath(node) {
        const ML = root.MathLive;
        if (ML && typeof ML.renderMathInElement === 'function') {
            try {
                ML.renderMathInElement(node);
            } catch (err) {
                // TODO
            }
        }
    }

    function valueText(state, block, key) {
        const F = format();
        if (block === 'cart') return F.fmtNum(state.cartesian[key], 2);
        if (state.defined && state.defined[key] === false) return F.UNDEFINED_TEXT;
        const v = state.native[key];
        return F.isAngleCoord(key) ? F.fmtAngle(v).text : F.fmtNum(v, 2);
    }

    function create(gd, host) {
        const st = { active: false, structure: null, name: null };
        const refs = { rows: [], name: null, system: null, body: null, t: null };

        const card = el('div', 'coords-card');
        const title = el('div', 'coords-card-title');
        refs.name = el('span', 'coords-card-name');
        refs.system = el('span', 'coords-card-system');
        title.appendChild(refs.name);
        title.appendChild(refs.system);
        refs.body = el('div', 'coords-card-body');
        card.appendChild(title);
        card.appendChild(refs.body);
        host.appendChild(card);

        function paletteFor(system) {
            const meta = gd._fullLayout && gd._fullLayout.meta;
            const g = meta && meta.grapher;
            return (g && g.palette && g.palette[system]) || {};
        }

        function resizeGraph() {
            try {
                if (root.Plotly && root.Plotly.Plots && gd.isConnected) root.Plotly.Plots.resize(gd);
            } catch (err) {
                // TODO
            }
        }

        function showIdle() {
            st.structure = null;
            st.name = null;
            refs.rows = [];
            refs.t = null;
            refs.body.textContent = '';
            refs.body.appendChild(el('div', 'coords-title'), IDLE_TEXT);
            refs.name.textContent = '';
            refs.system.textContent = '';
            card.classList.add('is-idle');
        }

        function build(state) {
            const system = state.system;
            const palette = paletteFor(system);
            refs.body.textContent = '';
            refs.rows = [];
            refs.t = null;
            card.classList.remove('is-idle');

            (BLOCKS[system] || []).forEach(function (block) {
                const section = el('div', 'coords-section');
                section.appendChild(el('div', 'coords-section-title'), block.title);
                block.keys.forEach(function (key) {
                    const row = el('div', 'coords-row');
                    const label = el('span', 'coords-key', LATEX[key] ? `\\(${LATEX[key]}\\)` : key);
                    if (block.id === 'native' || system === 'cartesian') {
                        const color = palette[key];
                        if (color) label.style.color = color;
                    }
                    const value = el('span', 'coords-val');
                    row.appendChild(label);
                    row.appendChild(value);
                    section.appendChild(row);
                    refs.rows.push({ block: block.id, key: key, value: value, text: null });
                });
                refs.body.appendChild(section);
            });

            if (state.t !== undefined) {
                const row = el('div', 'coords-row coords-row-t');
                row.appendChild(el('span', 'coords-key', '\\(t\\)'));
                refs.t = el('span', 'coords-val');
                row.appendChild(refs.t);
                refs.body.appendChild(row);
            }
            if (CONVENTION[system]) refs.body.appendChild(el('div', 'coords-convention', CONVENTION[system]));

            refs.system.textContent = SYSTEM_NAME[system] || system;
            renderMath(refs.body);
        }

        function update(state) {
            if (!st.active) return;
            if (!state) {
                if (st.structure !== null) showIdle();
                return;
            }
            const structure = state.system + (state.t !== undefined ? '+t' : '');
            if (structure !== st.structure) {
                build(state);
                st.structure = structure;
            }
            const name = state.name === undefined || state.name === null ? '' : String(state.name);
            if (name !== st.name) {
                st.name = name;
                refs.name.textContent = name ? '$$' + name + '$$' : '';
                if (name) renderMath(refs.name);
            }
            for (let i = 0; i < refs.rows.length; i++) {
                const r = refs.rows[i];
                const text = valueText(state, r.block, r.key);
                if (text !== r.text) {
                    r.value.textContent = text;
                    r.text = text;
                }
            }
            if (refs.t) refs.t.textContent = format().fmtNum(state.t, 3);
        }

        function setActive(on) {
            const was = st.active;
            st.active = !!on;
            if (st.active) {
                showIdle();
                host.classList.add('is-on');
            } else {
                host.classList.remove('is-on');
                st.structure = null;
            }
            if (was !== st.active) resizeGraph();
        }

        function reset() {
            if (st.active) showIdle();
        }

        return { setActive: setActive, update: update, reset: reset, element: card };
    }

    const api = {
        IDLE_TEXT: IDLE_TEXT,
        valueText: valueText,
        create: create,
    };

    if (typeof module === 'object' && module && module.exports) {
        module.exports = api;
    } else {
        root.GrapherReadout = api;
    }
})(typeof globalThis !== 'undefined' ? globalThis : this)
