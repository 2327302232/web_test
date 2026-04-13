// Utility wrapper to load AMap JS API dynamically and provide common helpers
export function setSecurityCode(securityJsCode) {
  if (securityJsCode) {
    try {
      window._AMapSecurityConfig = { securityJsCode };
    } catch (e) {
      console.warn('设置 AMap 安全配置失败', e);
    }
  }
}

export function loadAmapSdk() {
  return new Promise((resolve, reject) => {
    if (window.AMap) return resolve(window.AMap);

    const key = import.meta.env.VITE_AMAP_KEY;
    const securityJsCode = import.meta.env.VITE_AMAP_SECURITY_JS_CODE;

    if (!key) {
      return reject(new Error('缺少 VITE_AMAP_KEY（请检查 .env.local）'));
    }

    if (securityJsCode) setSecurityCode(securityJsCode);

    const script = document.createElement('script');
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}`;
    script.async = true;
    script.onload = () => {
      if (window.AMap) resolve(window.AMap);
      else reject(new Error('AMap 全局对象不存在'));
    };
    script.onerror = () => reject(new Error('高德 SDK 加载失败（网络或 Key 问题）'));
    document.head.appendChild(script);
  });
}

export function initMap(containerId, opts = {}) {
  if (!window.AMap) throw new Error('AMap SDK 尚未加载');
  return new window.AMap.Map(containerId, opts);
}

export function createMarker(map, position, options = {}) {
  if (!map) throw new Error('map 未初始化');
  const marker = new window.AMap.Marker(Object.assign({ position }, options));
  map.add(marker);
  return marker;
}

export function initGeolocation(options = {}) {
  return new Promise((resolve) => {
    window.AMap.plugin('AMap.Geolocation', () => {
      const geolocation = new window.AMap.Geolocation(Object.assign({
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 0,
        convert: true,
        showButton: false,
        showMarker: false,
        showCircle: false,
        zoomToAccuracy: true
      }, options));
      resolve(geolocation);
    });
  });
}

export function addPolyline(map, path = [], options = {}) {
  if (!map) throw new Error('map 未初始化');
  const polyline = new window.AMap.Polyline(Object.assign({ path, strokeColor: '#3366FF', strokeWeight: 4 }, options));
  polyline.setMap(map);
  return polyline;
}
