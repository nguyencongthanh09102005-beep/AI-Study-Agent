/* Open only authenticated source files supplied by our Flask API.
   Never point an unauthenticated browser at a private file URL. */
import {File, Paths} from 'expo-file-system';
import * as Sharing from 'expo-sharing';

export async function openOriginalDocument(payload, scope = 'document') {
  const name = String(payload?.name || '');
  const extension = (name.match(/\.(pdf|docx|txt|md)$/i) || [])[0]?.toLowerCase();
  if (!extension || !payload?.base64 || !payload?.type) {
    throw new Error('File gốc không hợp lệ hoặc định dạng chưa được hỗ trợ.');
  }
  // A server-issued path is never used as a local cache filename.
  const safeScope = scope.replace(/[^a-z0-9-]/gi, '').slice(0, 40) || 'document';
  const file = new File(Paths.cache, `aistudy-${safeScope}-${Date.now()}${extension}`);
  file.create();
  await file.write(payload.base64, {encoding:'base64'});
  try {
    await file.preview({title:name, mimeType:payload.type});
  } catch (previewError) {
    if (!(await Sharing.isAvailableAsync())) throw previewError;
    await Sharing.shareAsync(file.uri, {
      mimeType:payload.type, dialogTitle:'Mở file tài liệu gốc',
    });
  }
  // The OS file viewer may still be open: leave the temporary file in cache.
}
