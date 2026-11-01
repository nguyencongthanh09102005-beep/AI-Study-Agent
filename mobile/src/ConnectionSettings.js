import React, { useState } from 'react';
import {
  ActivityIndicator, SafeAreaView, ScrollView, StyleSheet,
  Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import { getApiBaseUrl, setApiBaseUrl, testApiConnection } from './api';

// Designed for local Expo Go demos: this changes only the URL of THIS
// running app instance. Put the verified URL into mobile/.env to persist.
export default function ConnectionSettings({onBack, onSaved}) {
  const [address,setAddress] = useState(getApiBaseUrl());
  const [busy,setBusy] = useState(false);
  const [notice,setNotice] = useState('');
  const [error,setError] = useState('');

  async function verifyAndSave() {
    if (busy) return;
    setBusy(true); setError(''); setNotice('');
    try {
      await testApiConnection(address);
      const saved = setApiBaseUrl(address);
      setNotice('Đã kết nối Flask thành công.');
      onSaved?.(saved);
    } catch (err) {
      setError(err?.message || 'Không kết nối được máy chủ.');
    } finally {
      setBusy(false);
    }
  }

  return <SafeAreaView style={styles.safe}>
    <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.page}>
      <TouchableOpacity onPress={onBack} style={styles.back} accessibilityRole="button">
        <Text style={styles.backText}>← Quay lại</Text>
      </TouchableOpacity>
      <Text style={styles.title}>Cài đặt kết nối</Text>
      <Text style={styles.subtitle}>Địa chỉ Flask trên máy tính của bạn</Text>
      <View style={styles.card}>
        <Text style={styles.label}>Máy chủ API</Text>
        <TextInput
          autoCapitalize="none" autoCorrect={false} keyboardType="url"
          accessibilityLabel="Địa chỉ máy chủ Flask"
          style={styles.input} value={address} onChangeText={setAddress}
          placeholder="http://192.168.1.10:5000" />
        <Text style={styles.hint}>
          Laptop và iPhone cần dùng cùng Wi-Fi. Lấy IPv4 thật của laptop từ
          lệnh ipconfig; không nhập 127.0.0.1 trên iPhone.
        </Text>
        {!!error && <Text style={styles.error}>{error}</Text>}
        {!!notice && <Text style={styles.success}>{notice}</Text>}
        <TouchableOpacity disabled={busy} style={[styles.button,busy&&styles.disabled]}
          onPress={verifyAndSave} accessibilityRole="button">
          {busy ? <ActivityIndicator color="#FFFFFF"/> :
            <Text style={styles.buttonText}>Kiểm tra và lưu kết nối</Text>}
        </TouchableOpacity>
      </View>
      <Text style={styles.info}>
        Địa chỉ đổi tại đây chỉ có hiệu lực khi ứng dụng còn chạy.
        Để lưu lâu dài, cập nhật EXPO_PUBLIC_API_URL trong mobile/.env
        và khởi động lại Expo.
      </Text>
      <Text style={styles.info}>Quản trị viên chỉ đăng nhập trên Web.</Text>
    </ScrollView>
  </SafeAreaView>;
}
const styles=StyleSheet.create({
  safe:{flex:1,backgroundColor:'#F6F8FC'},
  page:{flexGrow:1,paddingHorizontal:22,paddingTop:24,paddingBottom:30},
  back:{paddingVertical:12,alignSelf:'flex-start'},
  backText:{color:'#5D62D8',fontWeight:'800',fontSize:14},
  title:{color:'#202943',fontSize:26,fontWeight:'900',marginTop:20},
  subtitle:{color:'#576B8A',fontSize:14,marginTop:7,marginBottom:22},
  card:{backgroundColor:'#FFFFFF',padding:18,borderRadius:20,borderWidth:1,borderColor:'#E4E8F4'},
  label:{color:'#283C61',fontSize:14,fontWeight:'800',marginBottom:11},
  input:{backgroundColor:'#F9FAFE',borderWidth:1,borderColor:'#D8DEEF',
    borderRadius:13,padding:15,color:'#203052',fontSize:14},
  hint:{marginTop:12,fontSize:12,lineHeight:19,color:'#667998'},
  error:{color:'#B23B4B',marginTop:12,lineHeight:20},
  success:{color:'#188A68',marginTop:12,fontWeight:'800'},
  button:{alignItems:'center',justifyContent:'center',borderRadius:14,
    minHeight:52,backgroundColor:'#6567E8',marginTop:20},
  buttonText:{color:'#FFFFFF',fontSize:14,fontWeight:'800'},
  disabled:{opacity:0.55},
  info:{marginTop:16,color:'#637595',fontSize:12,lineHeight:20}
});
