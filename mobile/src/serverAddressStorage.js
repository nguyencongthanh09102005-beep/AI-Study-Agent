// Only a non-secret API origin is stored locally. Never cache cookies,
// user credentials, private study content or AI conversations here.
import AsyncStorage from '@react-native-async-storage/async-storage';
import { getApiBaseUrl, setApiBaseUrl } from './api';

const SERVER_ORIGIN_KEY = '@aistudyagent:flask-api-origin:v1';

export async function restoreServerAddress() {
  const saved = await AsyncStorage.getItem(SERVER_ORIGIN_KEY);
  if (!saved) return getApiBaseUrl();
  try {
    return setApiBaseUrl(saved);
  } catch (_error) {
    // Old/invalid addresses must not lock users out of connection settings.
    await AsyncStorage.removeItem(SERVER_ORIGIN_KEY);
    return getApiBaseUrl();
  }
}

export async function persistServerAddress(value) {
  // Called only after a successful live connection check.
  // The setter below validates the normalized value. If disk storage fails,
  // restore the previous in-memory server and surface the error.
  const previous = getApiBaseUrl();
  const current = setApiBaseUrl(value);
  try {
    await AsyncStorage.setItem(SERVER_ORIGIN_KEY, current);
    return current;
  } catch (error) {
    setApiBaseUrl(previous);
    throw new Error('Không lưu được địa chỉ máy chủ trên điện thoại. Hãy thử lại.');
  }
}
