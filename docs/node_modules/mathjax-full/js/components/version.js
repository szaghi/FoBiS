"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.VERSION = void 0;
exports.VERSION = (typeof PACKAGE_VERSION === 'undefined' ?
    (function () {
        var load = eval('require');
        var dirname = eval('__dirname');
        var path = load('path');
        return load(path.resolve(dirname, '..', '..', 'package.json')).version;
    })() :
    PACKAGE_VERSION);
//# sourceMappingURL=version.js.map