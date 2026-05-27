'use strict';

function nowMs() { return Date.now(); }
function iso() { return (new Date()).toISOString(); }

function safeStr(value) {
    try {
        return value === null || value === undefined ? String(value) : value.toString();
    } catch (error) {
        return '<toString error>';
    }
}

function emit(flow, payload) {
    send(Object.assign({ flow: flow, ts: iso() }, payload || {}));
}

function requestPatch(flow, payload) {
    var replyType = 'patch:' + flow + ':' + (payload.id || 'unknown');
    var patch = {};
    send(Object.assign({
        flow: flow,
        ts: iso(),
        awaitPatch: true,
        replyType: replyType
    }, payload || {}));
    recv(replyType, function(message) {
        patch = message.payload || {};
    }).wait();
    return patch;
}

function hasOwn(obj, key) {
    return Object.prototype.hasOwnProperty.call(obj, key);
}

Java.perform(function() {
    var AppBrandCommonBindingJni = Java.use('com.tencent.mm.appbrand.commonjni.AppBrandCommonBindingJni');

    var pendingById = new Map();
    var pendingByCallback = new Map();
    var nextRequestId = 1;

    function createRequestId() {
        var requestId = nextRequestId;
        nextRequestId += 1;
        return requestId;
    }

    function cleanupOlderThan(ms) {
        var cutoff = nowMs() - ms;
        for (var [id, record] of pendingById.entries()) {
            if (record.createdAt < cutoff) {
                pendingById.delete(id);
            }
        }
        for (var [callbackId, idList] of pendingByCallback.entries()) {
            var active = idList.filter(function(id) { return pendingById.has(id); });
            if (active.length > 0) {
                pendingByCallback.set(callbackId, active);
            } else {
                pendingByCallback.delete(callbackId);
            }
        }
    }

    function rememberRequest(record) {
        var callbackId = record.callbackId;
        var idList = pendingByCallback.get(callbackId) || [];
        pendingById.set(record.id, record);
        idList.push(record.id);
        pendingByCallback.set(callbackId, idList);
        cleanupOlderThan(60 * 1000);
    }

    function resolveRequest(callbackId) {
        var idList = pendingByCallback.get(callbackId | 0);
        if (!idList || idList.length === 0) {
            return null;
        }

        var requestId = idList.shift();
        if (idList.length > 0) {
            pendingByCallback.set(callbackId | 0, idList);
        } else {
            pendingByCallback.delete(callbackId | 0);
        }

        var record = pendingById.get(requestId) || null;
        if (record) {
            pendingById.delete(requestId);
        }
        return record;
    }

    var nativeInvokeHandler = AppBrandCommonBindingJni.nativeInvokeHandler.overload(
        'java.lang.String', 'java.lang.String', 'java.lang.String',
        'int', 'boolean', 'int', 'int'
    );
    var nativeInvokeHandlerOrig = nativeInvokeHandler;

    nativeInvokeHandler.implementation = function(api, data, ext, callbackId, isSync, workerId, misc) {
        var requestId = createRequestId();
        var body = safeStr(data);

        var patch = requestPatch('req', {
            id: requestId,
            api: safeStr(api),
            body: body
        });

        if (hasOwn(patch, 'api')) api = safeStr(patch.api);
        if (hasOwn(patch, 'body')) data = safeStr(patch.body);

        var record = {
            id: requestId,
            api: safeStr(api),
            body: safeStr(data),
            callbackId: callbackId | 0,
            createdAt: nowMs()
        };
        rememberRequest(record);

        emit('req', {
            id: record.id,
            api: record.api,
            body: record.body
        });

        return nativeInvokeHandlerOrig.call(this, api, data, ext, callbackId, isSync, workerId, misc);
    };

    try {
        var AppBrandJsBridgeBinding = Java.use('com.tencent.mm.appbrand.commonjni.AppBrandJsBridgeBinding');
        var invokeCallbackHandler = AppBrandJsBridgeBinding.invokeCallbackHandler.overload('int', 'java.lang.String', 'java.lang.String');
        var invokeCallbackHandlerOrig = invokeCallbackHandler;

        invokeCallbackHandler.implementation = function(callbackId, resp, ext) {
            var request = resolveRequest(callbackId);
            var body = safeStr(resp);

            var patch = requestPatch('resp', {
                id: request ? request.id : 0,
                body: body
            });
            if (hasOwn(patch, 'body')) resp = safeStr(patch.body);

            emit('resp', {
                id: request ? request.id : 0,
                body: safeStr(resp)
            });

            return invokeCallbackHandlerOrig.call(this, callbackId, resp, ext);
        };

        emit('status', { message: 'Hooked OUT: AppBrandJsBridgeBinding.invokeCallbackHandler' });
    } catch (error) {
        emit('error', {
            stage: 'RESP',
            message: 'Failed hook AppBrandJsBridgeBinding.invokeCallbackHandler',
            detail: safeStr(error)
        });
    }

    emit('status', {
        message: 'Hooks installed: nativeInvokeHandler -> AppBrandJsBridgeBinding.invokeCallbackHandler'
    });
});
