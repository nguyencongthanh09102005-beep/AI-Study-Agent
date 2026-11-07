import React, {useEffect,useState} from 'react';
import {Modal,ScrollView,StyleSheet,Text,TouchableOpacity,View} from 'react-native';
const {parseLocalDateTime,dateTimeString,localDateTimeLabel,monthCells} = require('./date-time-utils');

const pad = value => String(value).padStart(2,'0');
const WEEK = ['T2','T3','T4','T5','T6','T7','CN'];
function initial(value) {
  const parsed = parseLocalDateTime(value);
  if (parsed) return parsed;
  const now = new Date();
  return {year:now.getFullYear(),month:now.getMonth()+1,day:now.getDate(),hour:19,minute:0};
}

/** In-app calendar + clock, no extra native dependency, ISO string unchanged. */
export default function StudyDateTimePicker({label,value,onChange,disabled=false}) {
  const [open,setOpen]=useState(false);
  const [draft,setDraft]=useState(()=>initial(value));
  const [viewMonth,setViewMonth]=useState(()=>({year:initial(value).year,month:initial(value).month}));
  useEffect(()=>{
    if (!open) {
      const p=initial(value);
      setDraft(p);setViewMonth({year:p.year,month:p.month});
    }
  },[value,open]);

  const openPicker=()=>{
    const p=initial(value);
    setDraft(p);setViewMonth({year:p.year,month:p.month});setOpen(true);
  };
  const changeMonth=delta=>{
    setViewMonth(m=>{
      const d=new Date(m.year,m.month-1+delta,1);
      return {year:d.getFullYear(),month:d.getMonth()+1};
    });
  };
  const cells=monthCells(viewMonth.year,viewMonth.month);
  const minutes=Array.from(new Set([0,15,30,45,59,draft.minute])).sort((a,b)=>a-b);
  return <View style={styles.field}>
    <Text style={styles.label}>{label}</Text>
    <TouchableOpacity accessibilityRole="button" disabled={disabled}
      accessibilityLabel={label+': '+localDateTimeLabel(value)}
      accessibilityHint="Mở lịch chọn ngày và giờ"
      style={styles.trigger} onPress={openPicker}>
      <Text style={styles.dateText}>▦  {localDateTimeLabel(value)}</Text>
      <Text style={styles.arrow}>⌄</Text>
    </TouchableOpacity>
    <Modal visible={open} animationType="slide" transparent onRequestClose={()=>setOpen(false)}>
      <View style={styles.scrim}>
        <View style={styles.sheet}>
          <View style={styles.head}>
            <Text style={styles.heading}>{label}</Text>
            <TouchableOpacity accessibilityRole="button" accessibilityLabel="Đóng chọn giờ"
              onPress={()=>setOpen(false)} style={styles.close}><Text style={styles.closeText}>×</Text></TouchableOpacity>
          </View>
          <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
            <View style={styles.monthRow}>
              <TouchableOpacity style={styles.arrowButton} onPress={()=>changeMonth(-1)}
                accessibilityRole="button" accessibilityLabel="Tháng trước"><Text style={styles.arrowText}>‹</Text></TouchableOpacity>
              <Text style={styles.monthLabel}>Tháng {viewMonth.month}/{viewMonth.year}</Text>
              <TouchableOpacity style={styles.arrowButton} onPress={()=>changeMonth(1)}
                accessibilityRole="button" accessibilityLabel="Tháng sau"><Text style={styles.arrowText}>›</Text></TouchableOpacity>
            </View>
            <View style={styles.calendar}>
              {WEEK.map(d=><View key={d} style={styles.cell}><Text style={styles.weekLabel}>{d}</Text></View>)}
              {cells.map((day,i)=>(
                <View key={i} style={styles.cell}>
                  {day && <TouchableOpacity
                    accessibilityRole="button"
                    accessibilityLabel={`Ngày ${day}/${viewMonth.month}/${viewMonth.year}`}
                    accessibilityState={{selected:draft.day===day&&draft.month===viewMonth.month&&draft.year===viewMonth.year}}
                    style={[styles.day,draft.day===day&&draft.month===viewMonth.month&&draft.year===viewMonth.year&&styles.selected]}
                    onPress={()=>setDraft(d=>({...d,day,month:viewMonth.month,year:viewMonth.year}))}>
                    <Text style={[styles.dayText,draft.day===day&&draft.month===viewMonth.month&&draft.year===viewMonth.year&&styles.selectedText]}>{day}</Text>
                  </TouchableOpacity>}
                </View>
              ))}
            </View>
            <Text style={styles.subhead}>Giờ học</Text>
            <View style={styles.hours}>
              {Array.from({length:24},(_,i)=>i).map(hour=>
                <TouchableOpacity key={hour} accessibilityRole="button"
                  accessibilityLabel={pad(hour)+' giờ'} accessibilityState={{selected:draft.hour===hour}}
                  style={[styles.chip,draft.hour===hour&&styles.chipActive]}
                  onPress={()=>setDraft(d=>({...d,hour}))}>
                  <Text style={[styles.chipText,draft.hour===hour&&styles.chipTextActive]}>{pad(hour)}</Text>
                </TouchableOpacity>
              )}
            </View>
            <Text style={styles.subhead}>Phút</Text>
            <View style={styles.minutes}>
              {minutes.map(minute=>
                <TouchableOpacity key={minute} accessibilityRole="button" accessibilityLabel={pad(minute)+' phút'}
                  accessibilityState={{selected:draft.minute===minute}}
                  style={[styles.minuteChip,draft.minute===minute&&styles.chipActive]}
                  onPress={()=>setDraft(d=>({...d,minute}))}>
                  <Text style={[styles.chipText,draft.minute===minute&&styles.chipTextActive]}>{pad(minute)}</Text>
                </TouchableOpacity>
              )}
            </View>
            <Text style={styles.preview}>Đã chọn: {localDateTimeLabel(dateTimeString(draft))}</Text>
          </ScrollView>
          <View style={styles.actions}>
            <TouchableOpacity style={styles.cancel} onPress={()=>setOpen(false)} accessibilityRole="button">
              <Text style={styles.cancelText}>Hủy</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.save} accessibilityRole="button" onPress={()=>{
              onChange(dateTimeString(draft));setOpen(false);
            }}>
              <Text style={styles.saveText}>Xác nhận ngày giờ</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  </View>;
}

const C='#5E63D8';
const styles=StyleSheet.create({
  field:{marginBottom:16},label:{fontSize:13,fontWeight:'700',color:'#29324D',marginBottom:8},
  trigger:{minHeight:52,backgroundColor:'white',borderWidth:1,borderColor:'#DCE3F1',
    borderRadius:12,paddingHorizontal:14,flexDirection:'row',alignItems:'center',justifyContent:'space-between'},
  dateText:{fontSize:15,color:'#283B60',fontWeight:'700'},arrow:{fontSize:19,color:C},
  scrim:{flex:1,backgroundColor:'rgba(20,28,51,.48)',justifyContent:'flex-end'},
  sheet:{backgroundColor:'#F7F9FE',borderTopLeftRadius:22,borderTopRightRadius:22,
    maxHeight:'92%',paddingTop:18,paddingBottom:12},
  head:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',paddingHorizontal:18,marginBottom:8},
  heading:{fontSize:18,color:'#26365C',fontWeight:'800'},close:{width:44,height:44,alignItems:'center',justifyContent:'center'},
  closeText:{fontSize:27,color:'#6577A0'},content:{paddingHorizontal:18,paddingBottom:22},
  monthRow:{flexDirection:'row',alignItems:'center',justifyContent:'space-between',marginVertical:10},
  arrowButton:{minWidth:44,minHeight:44,justifyContent:'center',alignItems:'center',backgroundColor:'#E8EDFB',borderRadius:12},
  arrowText:{fontSize:26,color:C,fontWeight:'800'},monthLabel:{fontSize:15,fontWeight:'800',color:'#263B69'},
  calendar:{flexDirection:'row',flexWrap:'wrap',marginTop:5,marginBottom:8},
  cell:{width:'14.2857%',alignItems:'center',justifyContent:'center',minHeight:40},
  weekLabel:{fontSize:11,fontWeight:'800',color:'#6B7EA5'},day:{width:39,minHeight:40,borderRadius:11,alignItems:'center',justifyContent:'center'},
  selected:{backgroundColor:C},selectedText:{color:'white'},dayText:{fontWeight:'700',color:'#344A78',fontSize:13},
  subhead:{fontSize:13,color:'#33456C',fontWeight:'800',marginTop:12,marginBottom:8},
  hours:{flexDirection:'row',flexWrap:'wrap',gap:5},
  chip:{minWidth:'15.4%',minHeight:40,alignItems:'center',justifyContent:'center',
    backgroundColor:'#E9EEFA',borderRadius:9},
  chipActive:{backgroundColor:C},chipText:{color:'#455B83',fontSize:13,fontWeight:'800'},chipTextActive:{color:'white'},
  minutes:{flexDirection:'row',flexWrap:'wrap',gap:6},
  minuteChip:{minWidth:45,minHeight:42,alignItems:'center',justifyContent:'center',borderRadius:9,backgroundColor:'#E9EEFA'},
  preview:{fontSize:12,color:'#62739A',marginTop:15,textAlign:'center'},
  actions:{flexDirection:'row',gap:10,paddingHorizontal:18,paddingTop:10,borderTopWidth:1,borderColor:'#DFE6F4'},
  cancel:{flex:1,minHeight:49,alignItems:'center',justifyContent:'center',borderRadius:12,backgroundColor:'#E9EEFA'},
  cancelText:{fontWeight:'800',color:'#475A83'},
  save:{flex:2,minHeight:49,alignItems:'center',justifyContent:'center',borderRadius:12,backgroundColor:C},
  saveText:{fontSize:14,fontWeight:'800',color:'white'},
});
