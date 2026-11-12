const TOKEN_KEY = 'token'

/** 读取当前浏览器标签页的认证 Token。 */
export function getToken() {
  return sessionStorage.getItem(TOKEN_KEY) || ''
}

/** 保存当前浏览器标签页的认证 Token。 */
export function setToken(token) {
  sessionStorage.setItem(TOKEN_KEY, token)
}

/** 清理当前浏览器标签页的认证 Token。 */
export function removeToken() {
  sessionStorage.removeItem(TOKEN_KEY)
}

/** 解析 JWT claims，仅用于前端显示和路由判断，不代替后端验签。 */
export function parseToken(token = getToken()) {
  try {
    const encoded = token.split('.')[1]
    const normalized = encoded.replace(/-/g, '+').replace(/_/g, '/')
    const binary = atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '='))
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0))
    return JSON.parse(new TextDecoder().decode(bytes))
  } catch {
    return null
  }
}
