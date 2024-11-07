# AndroidWXCloudFuncHook

## 1. 微信云函数的介绍及目前的研究到的点

其实微信云函数不是单独的云函数，他包含：云网关、云托管、云函数，在此统称为云函数。

现在很多小程序的请求，不再是普通的HTTP请求，而是基于微信云网关/云函数/云托管进行请求，此类请求直接通过抓包软件，无法抓到，因为其实现原理主要是通过微信的Mmtls进行请求发包（当然这只是一种方式），根据研究，目前发现微信云请求有以下几种：

1. 基于微信Mmtls协议，调用微信的 ***<u>OperateWxData</u>*** 接口(可以在PC小程序逆向中看到该函数)是通过小程序进程和微信进程通讯，通过微信的mmtls协议进行实际的发包，走的相当于微信私有链路的请求。
2. 基于HTTP2.0，此类又分为两种，一种是鉴权模式，及微信小程序中部分使用的模式，该模式的主要流程是以下几点：
   1. 通过调用OperateWxData接口(此接口为Mmtls)的qbase_commit，中的  **<u>*tcbapi_get_service_info*</u>** 接口，获取到请求的加密参数以及鉴权的Token。
   2. 通过拿到的key和token把请求体进行加密并压缩(目前来看压缩使用的算法是snappy)，数据的格式一般采用ProtoBuf或者JSON两种类型进行处理。
   3. 拿到请求后，通过key进行解密，解密算法目前使用的是AES-CBC算法。
3. 不鉴权的HTTP2.0，此类与上述类似，一般用于使用了微信云托管/云网关但不在小程序，而是自己单独网站的情况下使用，key和token通过微信链路获取，后续请求和<u>2</u>中类似进行加解密。
4. 基于HTTP明文的请求，此类主要是微信云网关，一般用于其他App，此类请求，通过带Socks的抓包软件可以抓到(不带Socks的抓不到)，此类请求是通过微信云网关的算法(so层)，在请求的请求头中附带了x-wx-auth-code以及x-wx-call-id请求头，这两个参数通过URL以及Body计算出来，来进行数据合法性验证。

## 2. 这个项目用于干啥？

**AndroidWXCloudFuncHook** 主要是针对于上面介绍的第二种情况，第二种情况通过 *get_service_info* 接口拿到Key进行加解密，会导致抓包很麻烦(除非直接抓JS层)，同时要集成抓包+frida逆向到key进行同步作用，较为麻烦，所以在近期的研究中，发现当 *get_service_info* 接口触发某个异常的时候，会自动降级为第一种的Mmtls接口，如果降级成Mmtls那就可以很便捷的通过Frida找到对应的Hook点进行抓包。

目前抓包适配了安卓微信***848/849/850***，降级云函数只适配了***848/849***

```javascript
Java.use('com.tencent.mm.plugin.appbrand.jsapi.i0').o.overload('java.lang.String', 'java.util.Map').implementation = function (x, y) { // 取自代码片段,frida脚本部分
        let res  =this.o(x, y)
        sendResponseToPython(res)
        if(res.includes('{"data":"{\\"data\\":\\"{\\\\\\"token\\\\\\":\\\\\\"')){
       		res = '{"data":"{\\"baseresponse\\":{\\"errcode\\":103006,\\"errmsg\\":\\"system error.\\"}}","err_no":0}'
        	console.log("降级云函数")
    	}
    return res
}
```

在这里我们可以看到，当遇到获取Token和Key的时候，就抛出**103006异常**(目前来看就是非法请求)，此时云函数会自动降级为OperateWxData，就可以很方便的进行抓包，当然你也可以先抓到这个key进行解密，这里不做讨论。
当然你也可以通过此脚本自行实现RPC或者重写请求/响应
## 3. 如何运行?

1. python > 3.8
2. pip install -r (requirements.txt)
3. Git下载Frida-server(具体教程可以自行搜索) [Releases · frida/frida](https://github.com/frida/frida/releases)
4. 下载adb并添加到环境变量
5. 运行脚本即可

#### 另外，对于3/4类的请求，都能通过逆向JS或者So层拿到实际的加密参数，根据目前的算法，4类算法，基本就是一个很简单的HASH算法进行了验签，在So层通过IDA即可拿到。

By WeChat: ***RSCompanyCEO***

Telegram: ***ryf5584***
