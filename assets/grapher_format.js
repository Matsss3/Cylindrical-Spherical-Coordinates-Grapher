/*
 * Number and angle formatting for the coordinate-system interaction layer
 * (in-scene labels and the readout card). Pure functions, no DOM.
 */
(function (root) {
    'use strict';
    
    const PI_CHAR = '\u03c0';
    const MINUS = '\u2212';
    const DEGREE = '\u00b0';
    const MIDDOT = '\u00b7';

    const UNDEFINED_TEXT = 'indefinido';

    const FRACTION_DENOMINATORS = [1, 2, 3, 4, 6, 8, 12];
    const FRACTION_TOLERANCE = 1e-3;

    const SYMBOLS = {
        x: 'x',
        y: 'y',
        z: 'z',
        r: 'r',
        rho: '\u03c1',
        theta: '\u03b8',
        varphi: '\u03c6',
        t: 't',
    };

    const ANGLE_COORDS = { theta: true, varphi: true };

    function isNum(value) {
        return typeof value === 'number' && isFinite(value);
    }

    function withMinus(text) {
        return text.charAt(0) === '-' ? MINUS + text.slice(1) : text;
    }

    function symbol(name) {
        return Object.prototype.hasOwnProperty.call(SYMBOLS, name) ? SYMBOLS[name] : name;
    }

    function isAngleCoord(name) {
        return ANGLE_COORDS[name] === true;
    }


    /**
    * Fixed-decimal number. "-0.00" is never produced; non-finite input gives
    * UNDEFINED_TEXT. Negative numbers use the typographic minus sign.
    */
    function fmtNum(value, digits) {
        if (!isNum(value)) return UNDEFINED_TEXT;
        const d = digits === undefined || digits === null ? 2 : digits;
        let text = value.toFixed(d);
        if (Number(text) === 0) text = (0).toFixed(d);
        return withMinus(text);
    }

    function fractionOfPi(p, q) {
        if (p === 0) return '0';
        const sign = p < 0 ? MINUS : '';
        const a = Math.abs(p);
        const numerator = a === 1 ? PI_CHAR : String(a) + PI_CHAR;
        return sign + (q === 1 ? numerator : numerator + '/' + String(q));
    }


    /**
    * Angle (radians) as a multiple of pi.
    */
    function fmtPi(angle) {
        if (!isNum(angle)) return UNDEFINED_TEXT;
        const m = angle / Math.PI;
        for (let i = 0; i < FRACTION_DENOMINATORS.length; i++) {
            const q = FRACTION_DENOMINATORS[i];
            const p = Math.round(m * q);
            if (Math.abs(m - p / q) < FRACTION_TOLERANCE) return fractionOfPi(p, q);
        }
        const digits = Math.abs(m).toFixed(2);
        if (Number(digits) === 0) return '0';
        return (m < 0 ? MINUS : '') + digits + PI_CHAR;
    }

    /** Angle in radians, two decimals (no unit). */
    function fmtRad(angle) {
        return fmtNum(angle, 2);
    }

    /** Angle in degrees, at most one decimal. */
    function fmtDeg(angle) {
        if (!isNum(angle)) return UNDEFINED_TEXT;
        const rounded = Math.round((angle * 180 / Math.PI) * 10) / 10;
        return withMinus(String(rounded)) + DEGREE;
    }

    /**
    * All three renderings of an angle, as used by the readout card:
    * { pi: "0.40pi", rad: "1.26", deg: "72deg", text: "0.40pi . 1.26 rad . 72deg" }
    */
    function fmtAngle(angle) {
        if (!isNum(angle)) {
            return {
                pi: UNDEFINED_TEXT,
                rad: UNDEFINED_TEXT,
                deg: UNDEFINED_TEXT,
                text: UNDEFINED_TEXT,
            };
        }
        const pi = fmtPi(angle);
        const rad = fmtRad(angle);
        const deg = fmtDeg(angle);
        return {
            pi: pi,
            rad: rad,
            deg: deg,
            text: `${pi} ${MIDDOT} ${rad}rad ${MIDDOT} ${deg}`,
        };
    }

    /**
    * Short single-line in-scene label for one coordinate:
    * fmtCoord("rho", 4.27) -> "rho = 4.27", fmtCoord("theta", 0.4*pi) -> "theta = 0.40pi".
    */
    function fmtCoord(name, value) {
        const body = isAngleCoord(name) ? fmtPi(value) : fmtNum(value, 2);
        return `${symbol(name)} = ${body}`;
    }

    const api = {
        MINUS: MINUS,
        UNDEFINED_TEXT: UNDEFINED_TEXT,
        SYMBOLS: SYMBOLS,
        symbol: symbol,
        isAngleCoord: isAngleCoord,
        fmtNum: fmtNum,
        fmtPi: fmtPi,
        fmtRad: fmtRad,
        fmtDeg: fmtDeg,
        fmtAngle: fmtAngle,
        fmtCoord: fmtCoord,
    };

    if (typeof module === 'object' && module && module.exports) {
        module.exports = api;
    } else {
        root.GrapherFormat = api;
    }
})(typeof globalThis !== 'undefined' ? globalThis : this);
