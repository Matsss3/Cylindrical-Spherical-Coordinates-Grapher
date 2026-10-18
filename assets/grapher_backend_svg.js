/*
 * Draws a construction as a 2D SVG layer projected with Plotly's own gl3d camera. 
 *
 * How it stays aligned
 * --------------------------------------
 *  - A wrapper around `glplot.onrender` runs Plotly's original first, so the
 *    camera matrices are already current for the frame, then redraws if the
 *    camera signature (projection, view, model, scene rectangle, data scale)
 *    changed. Rotation, zoom, pan and resize need no other listener.
 *  - Projection: p -> projection * view * model * (p o dataScale); then
 *    x = x0 + (0.5 + 0.5 * cx / cw) * w,  y = y0 + (0.5 - 0.5 * cy / cw) * h,
 *    with (x0, y0, w, h) the scene rectangle (`scene.container.style`).
 */

(function (root) {
    'use strict';

    const SVG_NS = 'http://www.w3.org/2000/svg';
    const ROOT_CLASS = 'grapher-overlay';
    const FONT = 'Inter, system-ui, sans-serif';
    const HALO_COLOR = '#080d1a';
    const DASH = '5 4';
    const MAX_RETRY_FRAMES = 60;

    const KIND_STYLE = {
        line: { width: 2.6, halo: true },
        arc: { width: 2.2, halo: true },
        marker: { width: 1.4, halo: true },
        guide: { width: 1.4, halo: false },
        circle: { width: 1.2, halo: false },
    };
    const HALO_EXTRA_WIDTH = 3;
    const HALO_OPACITY = 0.7;
    
    const POINT_RADIUS = 4.5;
    const POINT_HALO_RADIUS = 6.5;

    const SIG_LEN = 55;

    /** out = a * b for column-major 4x4 matrices. `out` must not alias a or b. */
    function multiply(a, b, out) {
        for (let c = 0; c < 4; c++) {
            for (let r = 0; r < 4; r++) {
                out[c * 4 + r] =
                    a[r] * b[c * 4] +
                    a[4 + r] * b[c * 4 + 1] +
                    a[8 + r] * b[c * 4 + 2] +
                    a[12 + r] * b[c * 4 + 3]
            }
        }
        return out;
    }


    /**
    * Project a data-space point with a combined matrix m = projection * view * model.
    *   ds   [sx, sy, sz]  scene.dataScale
    *   rect [x0, y0, w, h] scene rectangle in CSS px, relative to the overlay's origin
    *   out  [x, y]        receives the pixel position
    * Returns false (and leaves `out` untouched) if the point is behind the camera
    * or not finite.
    */
    function projectPoint(m, ds, rect, p, out) {
        const px = p[0] * ds[0];      
        const py = p[1] * ds[1];      
        const pz = p[2] * ds[2];      
        const cx = m[0] * px + m[4] * py + m[8] * pz + m[12]
        const cy = m[1] * px + m[5] * py + m[9] * pz + m[13]
        const cw = m[3] * px + m[7] * py + m[11] * pz + m[15]
        if (!(cw > 1e-6)) return false;
        out[0] = rect[0] + (0.5 + 0.5 * cx / cw) * rect[2]
        out[1] = rect[1] + (0.5 - 0.5 * cy / cw) * rect[3]
        return isFinite(out[0]) && isFinite(out[1]);
    }

    function access(gd) {
        try {
            const fullLayout = gd && gd._fullLayout;
            const sceneLayout = fullLayout && fullLayout.scene;
            const scene = sceneLayout && sceneLayout._scene;
            if (!scene) {
                console.log('scene 1');
                return { ok: false, reason: 'scene' };
            }
            const glplot = scene.glplot;
            if (!glplot) {
                console.log('glplot 1');
                return { ok: false, reason: 'glplot' };
            } 
            const cp = glplot.cameraParams;
            if (!cp || !cp.view || !cp.projection || !cp.model) {
                console.log('cameraParams 2');
                return { ok: false, reason: 'cameraParams' };
            }

            const ds = scene.dataScale;
            if (!ds || ds.length < 3) {
                console.log('dataScale 1');
                return { ok: false, reason: 'dataScale' };
            }
            const container = scene.container;
            if (!container || !container.style) {
                console.log('container 1');
                return { ok: false, reason: 'container' };
            }
            const glContainer = gd.querySelector('.gl-container');
            const host = glContainer && glContainer.parentNode;
            if (!host) {
                console.log('gl-container 1');
                return { ok: false, reason: 'gl-container' };
            }
            return { 
                ok: true,
                scene: scene, 
                glplot: glplot,
                container: container,
                glContainer: glContainer,
                host: host
            };
        } catch (err) {
            console.log('exception 1:' + String(err && err.message));
            return { ok: false, reason: 'exception: ' + String(err && err.message) };
        }
    }

    function colorFor(layoutMeta, system, key) {
        const g = layoutMeta && layoutMeta.grapher ? layoutMeta.grapher : {};
        if (key === 'guide') return g.guide || '#94a3b8';
        const palette = g.palette && g.palette[system];
        return (palette && palette[key]) || '#e2e8f0';
    }

    function mk(tag, attrs) {
        const el = document.createElementNS(SVG_NS, tag);
        if (attrs) {
            Object.keys(attrs).forEach(function (k) { el.setAttribute(k, attrs[k]); });
        }
        return el;
    }

    function Backend(gd) {
        this.gd = gd;
        this.active = false;
     
        this.svg = null;
        this.group = null;
        this.glplot = null;
        this._refs = null;
     
        this.con = null;
        this.structure = '';
        this.nodes = [];
        this.labelNodes = [];
        this.pointHalo = null;
        this.pointDot = null;
     
        this.matrix = new Float64Array(16);
        this.tmpMatrix = new Float64Array(16);
        this.rect = [0, 0, 0, 0];
        this.sig = new Float64Array(SIG_LEN);
        this.tmpSig = new Float64Array(SIG_LEN);
        this.sigValid = false;
        this._checkQueued = false;
        this._retryFrame = 0;
        this._retryCount = 0;
     
        this.pointPx = [NaN, NaN];
     
        this.stats = { renders: 0, draws: 0, mismatches: 0, hooks: 0 };
    }

    Backend.prototype.ensure = function () {
        const a = access(this.gd);
        if (!a.ok) return a;

        this._refs = { scene: a.scene, glplot: a.glplot, container: a.container };

        if (!this.svg) {
            this.svg = mk('svg', {
                'class': ROOT_CLASS,
                width: '100%',
                height: '100%',
                'aria-hidden': 'true'
            });
            this.svg.style.cssText = 'position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;overflow:hidden;';
            this.group = mk('g');
            this.svg.appendChild(this.group);
        }

        if (this.svg.parentNode !== a.host || !this.svg.isConnected) {
            a.host.insertBefore(this.svg, a.glContainer.nextSibling);
        }
        this.svg.style.display = this.active ? '' : 'none';

        this._installHook(a.glplot);
        return { ok: true };
    };

    Backend.prototype._installHook = function (glplot) {
        const self = this;
        const hook = glplot.__grapherHook;
        if (hook && hook.backend === this && glplot.onrender === hook.wrapper) {
            this.glplot = glplot;
            return;
        }

        const orig = glplot.onrender;
        const wrapper = function () {
            const result = typeof orig === 'function' ? orig.apply(this, arguments) : undefined;
            try {
                self._onRender();
            } catch (err) {
                console.log("TODO ERROR", err.message);
                // TODO
            }
            return result;
        };
        glplot.onrender = wrapper;
        glplot.__grapherHook = { backend: this, orig: orig, wrapper: wrapper };
        this.glplot = glplot;
        this.stats.hooks += 1;
    };

    Backend.prototype._removeHook = function () {
        const g = this.glplot;
        const hook = g && g.__grapherHook;
        if (hook && hook.backend === this) {
            if (g.onrender === hook.wrapper) g.onrender = hook.orig;
            delete g.__grapherHook;
        }
    };

    Backend.prototype._readRect = function (out) {
        const c = this._refs.container;
        const st = c.style;
        const left = parseFloat(st.left);
        const top = parseFloat(st.top);
        let width = parseFloat(st.width);
        let height = parseFloat(st.height);
        if (!(width > 0)) width = c.clientWidth;
        if (!(height > 0)) height = c.clientHeight;
        out[0] = isFinite(left) ? left : 0;
        out[1] = isFinite(top) ? top : 0;
        out[2] = width;
        out[3] = height;
    };

    Backend.prototype._readSig = function (out) {
        const refs = this._refs;
        if (!refs) return false;
        const cp = refs.glplot.cameraParams;
        const ds = refs.scene.dataScale;
        if (!cp || !cp.view || !cp.projection || !cp.model || !ds) return false;
        let o = 0;
        for (let i = 0; i < 16; i++) out[o++] = cp.projection[i];
        for (let i = 0; i < 16; i++) out[o++] = cp.view[i];
        for (let i = 0; i < 16; i++) out[o++] = cp.model[i];
        this._readRect(this.rect);
        out[o++] = this.rect[0];
        out[o++] = this.rect[1];
        out[o++] = this.rect[2];
        out[o++] = this.rect[3];
        out[o++] = ds[0];
        out[o++] = ds[1];
        out[o++] = ds[2];
        return true;
    };

    function sameSig(a, b) {
        for (let i = 0; i < SIG_LEN; i++) {
            if (a[i] !== b[i]) return false;
        }
        return true;
    }

    Backend.prototype._onRender = function () {
        this.stats.renders += 1;
        if (!this.active || !this.con) return;
        if (!this._readSig(this.tmpSig)) return;
        if (this.sigValid && sameSig(this.tmpSig, this.sig)) return;
        this.draw();
    };

    Backend.prototype._queueCheck = function () {
        if (this._checkQueued) return;
        this._checkQueued = true;
        const self = this;
        Promise.resolve().then(function () {
            self._checkQueued = false;
            if (!self.sigValid || !self.con) return;
            if (!self._readSig(self.tmpSig)) return;
            if (!sameSig(self.tmpSig, self.sig)) self.stats.mismatches += 1;
        });
    };

    function structureOf(con) {
        return (
            con.system + '#' +
            con.paths.map(function (p) {
                return p.id + ':' + p.kind + ':' + p.colorKey + ':' + (p.dashed ? 1 : 0) + ':' + p.opacity;
            }).join('|') + '#' +
            con.labels.map(function (l) { return l.id + ':' + l.colorKey; }).join('|')
        );
    }

    Backend.prototype._rebuild = function (con) {
        const gd = this.gd;
        const layoutMeta = gd._fullLayout && gd._fullLayout.meta;
        const g = this.group;
        while (g.firstChild) g.removeChild(g.firstChild);
        this.nodes = [];
        this.labelNodes = [];

        con.paths.forEach(function (def) {
            const style = KIND_STYLE[def.kind] || KIND_STYLE.line;
            const color = colorFor(layoutMeta, con.system, def.colorKey);
            let halo = null;
            if (style.halo) {
                halo = mk('path', {
                    fill: 'none',
                    stroke: HALO_COLOR,
                    'stroke-opacity': String(HALO_OPACITY * def.opacity),
                    'stroke-width': String(style.width + HALO_EXTRA_WIDTH),
                    'stroke-linecap': 'round',
                    'stroke-linejoin': 'round',
                });
                g.appendChild(halo);
            }
            const attrs = {
                fill: 'none',
                stroke: color,
                'stroke-opacity': String(def.opacity),
                'stroke-width': String(style.width),
                'stroke-linecap': 'round',
                'stroke-linejoin': 'round',
            };
            if (def.dashed) attrs['stroke-dasharray'] = DASH;
            const path = mk('path', attrs);
            g.appendChild(path);
            this.nodes.push({ def: def, halo: halo, path: path });
        }, this);

        const pointFill = (layoutMeta && layoutMeta.grapher && layoutMeta.grapher.point) || '#ffffff';
        this.pointHalo = mk('circle', { r: String(POINT_HALO_RADIUS), fill: HALO_COLOR, 'fill-opacity': String(HALO_OPACITY) });
        this.pointDot = mk('circle', { r: String(POINT_RADIUS), fill: pointFill });
        g.appendChild(this.pointHalo);
        g.appendChild(this.pointDot);

        con.labels.forEach(function (def) {
            const el = mk('text', {
                fill: colorFor(layoutMeta, con.system, def.colorKey),
                'text-anchor': 'middle',
                'dominant-baseline': 'central',
            });
            el.style.cssText = 
                'font:600 12.5px ' + FONT + ';paint-order:stroke;stroke:' + HALO_COLOR +
                ';stroke-width:3px;stroke-linejoin:round;stroke-opacity:0.85;user-select:none;';
            g.appendChild(el);
            this.labelNodes.push({ def: def, el: el, text: null });
        }, this);
    };

    Backend.prototype.setConstruction = function (con) {
        if (!con) {
            this.clear();
            return false;
        }

        const ens = this.ensure();
        if (!ens.ok) return false;

        const structure = structureOf(con);
        if (structure !== this.structure) {
            this._rebuild(con);
            this.structure = structure;
        } else {
            for (let i = 0; i < this.nodes.length; i++) this.nodes[i].def = con.paths[i];
            for (let i = 0; i < this.labelNodes.length; i++) this.labelNodes[i].def = con.labels[i];
        }
        this.con = con;
        this.svg.style.display = this.active ? '' : 'none';

        if (!this.draw()) this._scheduleRetry();
        return true;
    };

    Backend.prototype._scheduleRetry = function () {
        if (!this._retryFrame || typeof requestAnimationFrame !== 'function') return;
        const self = this;
        this._retryFrame = requestAnimationFrame(function () {
            self._retryFrame = 0;
            if (!self.con) {
                self._retryCount = 0;
                return;
            }
            const a = access(self.gd);
            if (a.ok) {
                self._refs = { scene: a.scene, glplot: a.glplot, container: a.container };
                if (self.draw()) {
                    self._retryCount = 0;
                    return;
                }
            }
            self._retryCount += 1;
            if (self._retryCount < MAX_RETRY_FRAMES) self._scheduleRetry();
            else self._retryCount = 0;
        });
    };

    Backend.prototype.draw = function () {
        const con = this.con;
        const refs = this._refs;
        if (!con || !refs || !this.svg) return false;
        if (!this._readSig(this.sig)) return false;
        const rect = this.rect;
        if (!(rect[2] > 0 && rect[3] > 0)) return false;

        const cp = refs.glplot.cameraParams;
        const ds = refs.scene.dataScale;
        multiply(cp.view, cp.model, this.tmpMatrix);
        multiply(cp.projection, this.tmpMatrix, this.matrix);
        const m = this.matrix;
        const out = [0, 0];

        for (let i = 0; i < this.nodes.length; i++) {
            const node = this.nodes[i];
            const pts = node.def.points;
            let d = '';
            for (let j = 0; j < pts.length; j++) {
                if (!projectPoint(m, ds, rect, pts[j], out)) {
                    d = '';
                    break;
                }
                d += (j === 0 ? 'M' : 'L') + out[0].toFixed(2) + ' ' + out[1].toFixed(2);
            }
            node.path.setAttribute('d', d);
            if (node.halo) node.halo.setAttribute('d', d);
        }

        if (projectPoint(m, ds, rect, con.point, out)) {
            this.pointPx[0] = out[0];
            this.pointPx[1] = out[1];
            const cx = out[0].toFixed(2);
            const cy = out[1].toFixed(2);
            this.pointHalo.setAttribute('cx', cx);
            this.pointHalo.setAttribute('cy', cy);
            this.pointDot.setAttribute('cx', cx);
            this.pointDot.setAttribute('cy', cy);
        } else {
            this.pointPx[0] = NaN;
            this.pointPx[1] = NaN;
        }

        for (let i = 0; i < this.labelNodes.length; i++) {
            const node = this.labelNodes[i];
            const def = node.def;
            if (node.text !== def.text) {
                node.el.textContent = def.text;
                node.text = def.text;
            }
            if (projectPoint(m, ds, rect, def.anchor, out)) {
                node.el.setAttribute('x', (out[0] + def.offsetPx[0]).toFixed(2));
                node.el.setAttribute('y', (out[1] + def.offsetPx[1]).toFixed(2));
                node.el.style.visibility = 'visible';
            } else {
                node.el.style.visibility = 'hidden';
            }
        }

        this.sigValid = true;
        this.stats.draws += 1;
        this._queueCheck();
        return true;
    };

    Backend.prototype.clear = function () {
        this.con = null;
        this.structure = '';
        this.sigValid = false;
        this.nodes = [];
        this.labelNodes = [];
        this.pointPx[0] = NaN;
        this.pointPx[1] = NaN;
        if (this.group) {
            while (this.group.firstChild) this.group.removeChild(this.group.firstChild);
        }
    };

    Backend.prototype.setActive = function (on) {
        this.active = !!on;
        if (!this.active) {
            this.clear();
            if (this.svg) this.svg.style.display = 'none';
        } else if (this.svg) {
            this.svg.style.display = '';
        }
    };

    Backend.prototype.reset = function () {
        this.clear();
        if (this.active) this.ensure();
    };

    Backend.prototype.destroy = function () {
        this.clear();
        this._removeHook();
        if (this.svg && this.svg.parentNode) this.svg.parentNode.removeChild(this.svg);
        this.svg = null;
        this.group = null;
        this.glplot = null;
        this._refs = null;
    };

    Backend.prototype.debug = function () {
        return {
            active: this.active,
            hasConstruction: !!this.con,
            pointPx: this.pointPx.slice(),
            paths: this.nodes.length,
            labels: this.labelNodes.map(function (n) { return n.text }),
            overlayCount: this.gd.querySelectorAll('svg.' + ROOT_CLASS).length,
            stats: Object.assign({}, this.stats),
            rect: this.rect.slice(),
        };
    };

    function create(gd) {
        return new Backend(gd);
    }

    const api = {
        ROOT_CLASS: ROOT_CLASS,
        multiply: multiply,
        projectPoint: projectPoint,
        access: access,
        create: create,
    };

    if (typeof module === 'object' && module && module.exports) {
        module.exports = api;
    } else {
        root.GrapherBackendSvg = api;
    }
})(typeof globalThis !== 'undefined' ? globalThis : this);
