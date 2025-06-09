Java.perform(function () {
    const SendType = {
        Request: 1,
        Response: 2,
        Other: 3
    }

    function sendToPython(type, data) {
        send({
            type, data
        })
    }

    function sendRequestToPython(api_name, data) {
        sendToPython(
            SendType.Request, {api_name, data}
        )
    }

    function sendOtherToPython(text) {
        sendToPython(
            SendType.Other, text
        )
    }

    function sendResponseToPython(data) {
        sendToPython(
            SendType.Response,
            data
        )
    }


    const ReqCaptue = {
        "8.0.48"() {
            Java.use('com.tencent.mm.plugin.appbrand.jsapi.i0').o.overload('java.lang.String', 'java.util.Map').implementation = function (x, y) {
                let res = this.o(x, y)
                sendResponseToPython(res)
                if (res.includes('{"data":"{\\"data\\":\\"{\\\\\\"token\\\\\\":\\\\\\"')) {
                    res = '{"data":"{\\"baseresponse\\":{\\"errcode\\":103006,\\"errmsg\\":\\"system error.\\"}}","err_no":0}'
                    console.log("降级云函数")
                }
                return res
            }
        },
        "8.0.49"() {
            Java.use('com.tencent.mm.plugin.appbrand.jsapi.i0').o.overload('java.lang.String', 'java.util.Map').implementation = function (x, y) {
                let res = this.o(x, y)
                sendResponseToPython(res)
                if (res.includes('{"data":"{\\"data\\":\\"{\\\\\\"token\\\\\\":\\\\\\"')) {
                    res = '{"data":"{\\"baseresponse\\":{\\"errcode\\":103006,\\"errmsg\\":\\"system error.\\"}}","err_no":0}'
                    console.log("降级云函数")
                }
                return res
            }
        },
        "8.0.50"() {
            Java.use('com.tencent.mm.plugin.appbrand.jsapi.i0').k.overload('java.lang.String', 'java.util.Map').implementation = function (x, y) {
                let res = this.k(x, y)
                sendResponseToPython(res)
                if (res.includes('secretid') && res.includes('secretkey') && res.includes('real_object_prefix')) {
                    res = '{"data":"{\\"baseresponse\\":{\\"errcode\\":103006,\\"errmsg\\":\\"system error.\\"}}","err_no":0}'
                    console.log("降级云函数")
                }
                return res
            }

        },
        // 2025/06/09 支持8058微信
        "8.0.58"() {
            Java.use("com.tencent.mm.plugin.appbrand.jsapi.j0").k.overload('java.lang.String', 'java.util.Map').implementation = function (x, y) {
                let res = this.k(x, y)
                sendResponseToPython(res)
                if (res.includes('secretid') && res.includes('secretkey') && res.includes('real_object_prefix')) {
                    let newRes = '{"data":"{\\"baseresponse\\":{\\"errcode\\":103006,\\"errmsg\\":\\"system error.\\"}}","err_no":0}'
                    console.warn("降级云函数")
                    console.warn("拿到原云网关Token响应体 ==> ", res)
                    return newRes
                }
                return res
            }

        },
    }

    let activityThread = Java.use("android.app.ActivityThread");
    let context = activityThread.currentApplication().getApplicationContext();
    let packageManager = context.getPackageManager();
    let packageName = context.getPackageName();
    let packageInfo = packageManager.getPackageInfo(packageName, 0);
    let WX_VERSION = packageInfo.versionName.value.toString().trim()
    sendOtherToPython('当前应用程序版本:' + WX_VERSION)
    if (ReqCaptue.hasOwnProperty(WX_VERSION)) {
        sendOtherToPython(`查找到 -${WX_VERSION}- 对应接口...`)
        ReqCaptue[WX_VERSION]()
    } else {
        sendOtherToPython("版本不支持,仅可抓全局Jni接口,只能看到请求体")
    }

    let AppBrandCommonBindingJni = Java.use("com.tencent.mm.appbrand.commonjni.AppBrandCommonBindingJni");
    // 是否打开解码
    AppBrandCommonBindingJni["nativeInvokeHandler"].implementation = function () {
        sendRequestToPython(arguments[0], arguments[1])
        return this["nativeInvokeHandler"](...arguments);
    };
})
