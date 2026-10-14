"""Sparse semantic initial annotations in original-image pixels (not traced paths).
All six initializations use the same components and curve equations.
"""
import copy
import numpy as np
from .model import topology, refresh_states, WIDTH,HEIGHT

# The two entries of every tuple are viewer-left (character right), viewer-right.
DATA={
'smile':{
'brow':([[246,354],[345,250],[455,204],[542,207],[576,222]],[[1167,178],[1088,124],[968,91],[875,118],[836,148]]),
'upper':([[631,459],[598,379],[514,350],[392,404],[307,488]],[[874,399],[918,315],[1057,239],[1157,279],[1206,365]]),
'lower':([[628,482],[474,510],[327,558]],[[1218,385],[1060,400],[913,444]]),
'pupil':([[542,411],[1105,307]]),'radii':([[72,73],[69,72]]),'highlight':([[508,380],[1074,275]]),
'moustache':([[748,612],[682,607],[575,655],[486,683],[435,658],[438,614],[472,603],[486,624]],[[803,598],[866,575],[977,587],[1070,592],[1122,564],[1127,519],[1097,505],[1081,532]]),
'nose':[[747,558],[770,514],[816,511]],
'mouth':[[708,704],[745,713],[807,696],[872,660],[920,620]],
'inner_accent':([[445,308],[512,304],[575,335]],[[1065,210],[1113,218],[1151,241]]),
'outer_accent':([[298,433],[313,384],[354,347]],[[879,294],[913,226],[976,190]]),
'brow_accent':([[596,186],[608,215],[604,239]],[[817,104],[799,141],[810,174]]),
'under':([[435,548],[386,559],[344,578]],[[1190,412],[1140,416],[1090,430]]),
},
'tense':{
'brow':([[294,374],[384,289],[496,259],[599,212],[624,147]],[[1147,164],[1050,144],[932,153],[841,135],[815,88]]),
'upper':([[650,462],[624,375],[554,340],[413,409],[348,497]],[[880,401],[934,308],[1091,240],[1162,284],[1196,379]]),
'lower':([[638,483],[494,506],[378,546]],[[1201,384],[1055,396],[916,443]]),
'pupil':([[579,415],[1135,306]]),'radii':([[72,69],[69,70]]),'highlight':([[548,385],[1101,277]]),
'moustache':([[748,615],[674,611],[564,667],[467,698],[418,671],[426,629],[458,625],[466,650]],[[810,600],[875,576],[985,600],[1080,607],[1131,576],[1132,536],[1100,521],[1086,549]]),
'nose':[[753,554],[773,514],[817,509]],
'mouth':[[704,737],[722,687],[799,686],[877,638],[913,693]],'mouth_lower':[[733,737],[814,709],[885,701]],
'inner_accent':([[494,325],[548,304],[592,317]],[[1067,208],[1105,213],[1134,226]]),
'outer_accent':([[342,444],[358,401],[396,372]],[[888,307],[921,241],[971,202]]),
'brow_accent':([[662,190],[659,218],[646,237]],[[773,117],[777,147],[793,168]]),
},
'love':{
'brow':([[274,359],[365,274],[492,245],[594,207],[619,139]],[[1200,146],[1098,109],[957,132],[849,130],[820,86]]),
'upper':([[648,466],[619,378],[543,346],[410,405],[339,490]],[[874,398],[927,308],[1086,235],[1180,280],[1213,353]]),
'lower':([[638,481],[489,509],[370,541]],[[1218,364],[1057,393],[924,438]]),
'pupil':([[565,410],[1129,301]]),'radii':([[76,71],[79,72]]),'highlight':([[523,379],[1087,270]]),
'moustache':([[739,610],[667,607],[555,670],[464,699],[416,672],[424,627],[454,619],[465,644]],[[800,594],[868,570],[995,599],[1090,607],[1147,577],[1144,535],[1111,520],[1100,548]]),
'nose':[[747,555],[771,510],[816,504]],
'mouth':[[714,654],[747,661],[788,654],[839,632],[881,622]],'mouth_lower':[[736,719],[794,763],[851,715]],
'inner_accent':([[485,318],[548,304],[608,328]],[[1110,200],[1148,208],[1180,229]]),
'outer_accent':([[328,439],[348,391],[382,358]],[[881,308],[917,236],[976,195]]),
'brow_accent':([[637,176],[645,207],[637,231]],[[783,108],[782,136],[800,159]]),
},
'cheeky':{
'brow':([[267,360],[356,281],[480,260],[584,237],[613,178]],[[1188,133],[1091,91],[956,123],[850,130],[832,84]]),
'upper':([[644,462],[618,377],[545,348],[410,405],[329,491]],[[871,398],[925,306],[1080,239],[1184,285],[1200,354]]),
'lower':([[633,480],[490,508],[369,536]],[[1203,357],[1060,389],[927,439]]),
'pupil':([[570,410],[1127,300]]),'radii':([[76,70],[76,69]]),'highlight':([[537,383],[1091,271]]),
'moustache':([[748,606],[680,604],[565,662],[469,690],[423,665],[430,620],[461,615],[471,640]],[[803,595],[869,568],[989,592],[1084,601],[1132,571],[1132,525],[1102,511],[1085,539]]),
'nose':[[753,551],[774,508],[822,506]],
'mouth':[[714,712],[755,717],[810,695],[869,660],[908,625]],
'inner_accent':([[492,312],[550,308],[599,333]],[[1091,192],[1128,201],[1176,230]]),
'outer_accent':([[323,439],[343,391],[379,354]],[[879,298],[915,228],[977,192]]),
'brow_accent':([[637,195],[648,221],[638,242]],[[780,113],[781,143],[798,159]]),
},
'tongue':{
'brow':([[324,258],[430,169],[533,112],[590,121],[628,142]],[[1068,126],[1009,95],[945,78],[886,81],[855,115]]),
'upper':([[642,431],[638,308],[532,229],[419,260],[348,391]],[[880,462],[885,322],[1022,211],[1103,261],[1142,396]]),
'lower':([[642,448],[521,425],[384,477]],[[1173,404],[1027,398],[885,472]]),
'pupil':([[413,300],[1112,353]]),'radii':([[55,63],[48,52]]),'highlight':([[439,277],[1131,337]]),
'moustache':([[720,569],[651,553],[551,616],[464,648],[420,618],[426,578],[460,571],[469,598]],[[834,553],[902,527],[997,587],[1070,604],[1117,580],[1127,535],[1096,510],[1081,538]]),
'nose':[[742,525],[760,486],[802,491]],
'mouth':[[650,590],[685,607],[762,610],[844,590],[896,563]],'mouth_lower':[[704,645],[777,690],[867,628]],
'inner_accent':([[613,235],[639,261],[654,297]],[[991,175],[1040,169],[1081,192]]),
'outer_accent':([[332,317],[350,274],[387,243]],[[839,366],[842,295],[874,242]]),
'brow_accent':([[648,178],[659,206],[651,223]],[[810,88],[799,111],[813,134]]),
'under':([[637,464],[616,465],[592,473]],[[966,462],[932,470],[905,483]]),
},
'skeptical':{
'brow':([[300,262],[406,199],[525,226],[634,294],[686,303]],[[1170,150],[1075,95],[982,110],[862,238],[785,257]]),
'upper':([[644,496],[641,422],[518,366],[368,333],[337,377]],[[870,492],[866,400],[1006,290],[1148,298],[1140,431]]),
'lower':([[645,510],[513,464],[377,480]],[[1178,448],[1043,435],[875,506]]),
'pupil':([[565,411],[951,378]]),'radii':([[61,60],[62,68]]),'highlight':([[538,394],[966,364]]),
'moustache':([[692,608],[627,587],[537,640],[438,661],[397,634],[404,589],[440,579],[451,609]],[[828,608],[890,581],[1000,628],[1082,641],[1126,610],[1137,571],[1105,546],[1089,580]]),
'nose':[[725,564],[738,523],[791,523]],
'mouth':[[632,627],[685,654],[768,662],[850,642],[908,611]],
'inner_accent':([[577,338],[607,348],[631,363]],[[1008,246],[1066,213],[1130,235]]),
'outer_accent':([[330,337],[389,291],[471,306]],[[837,397],[838,346],[870,302]]),
'brow_accent':([[696,329],[709,350],[703,371]],[[738,251],[745,283],[772,309]]),
'under':([[634,526],[611,517],[592,515]],[[932,504],[908,511],[885,525]]),
}}

def seed_pose(name):
    d=DATA[name];t=topology()
    p={'schema_version':'1.0','topology_id':'cartoon_face_v1','coordinate_system':'normalized','canvas':{'width':WIDTH,'height':HEIGHT},
      'name':name,'keypoints':{},'rig':{},'variants':{},'style':{'background':'white','ink':'black'},
      'provenance':{'initializer':'sparse semantic annotations','reference_id':name}}
    for k in t['keypoints']:p['keypoints'][k['name']]={'id':k['id'],'xy':[.5,.5],'state':'visible'}
    for c,spec in t['components'].items():
        n=len(spec['anchors']);p['rig'][c]={'opacity':1.0}
        if spec['kind'] in ('ribbon','contour'):p['rig'][c]['tangent_scales']=[1.0]*n
        if spec['kind']=='ribbon':p['rig'][c]['widths']=[0.3]+[8.0]*(n-2)+[0.3]
    def put(c,pts,widths=None,opacity=None):
        for n,pt in zip(t['components'][c]['anchors'],pts):p['keypoints'][n]['xy']=((np.asarray(pt)-[42,56])/[WIDTH,HEIGHT]).tolist()
        if widths is not None:p['rig'][c]['widths']=widths
        if opacity is not None:p['rig'][c]['opacity']=opacity
    for j,side in enumerate(('right','left')):
        put(side+'_brow',d['brow'][j],[1,25,53,65,12] if j==0 else [1,22,47,69,12])
        if name=='tongue':p['rig'][side+'_brow']['widths']=[1,13,31,30,8]
        if name=='skeptical':p['rig'][side+'_brow']['widths']=[1,25,53,65,10]
        put(side+'_eye_upper',d['upper'][j],[2,15,27,27,6])
        lower_pts=d['lower'][j] if j==0 else d['lower'][j][::-1]
        put(side+'_eye_lower',lower_pts,[1,11,4])
        p['rig'][side+'_eye_lower']['corner_accents']=([0,1] if j==0 else [0,1]) if name in ('tongue','skeptical') else [0,0]
        upper=np.asarray(d['upper'][j]);lower=np.asarray(lower_pts)
        if j==0:
            side_end=upper[-1]+[-1,42];lash=upper[-1]+[-55,12]
        else:
            side_end=upper[-1]+[-5,12];lash=upper[-2]+[70,31]
        if name=='tongue' and j==0:side_end=[378,472];lash=[279,404]
        if name=='tongue' and j==1:lash=[1175,223]
        if name=='skeptical' and j==0:side_end=[377,480];lash=[272,369]
        if name=='skeptical' and j==1:lash=[1225,255]
        put(side+'_eye_side',[side_end]);p['rig'][side+'_eye_side'].update({'width':9,'bulge':-14 if j==0 else 14,'opacity':1 if j==0 else 0})
        put(side+'_lash',[lash]);p['rig'][side+'_lash'].update({'width':24,'root_t':.94 if j==0 else .76,'bend':15})
        put(side+'_pupil',[d['pupil'][j]]);p['rig'][side+'_pupil'].update({'rx':d['radii'][j][0],'ry':d['radii'][j][1],'angle':-12 if j==0 else -17,'openness':1.0})
        put(side+'_highlight',[d['highlight'][j]]);p['rig'][side+'_highlight'].update({'rx':18,'ry':19,'angle':0,'heart_scale':1,'heart_offset':[16,19],'heart_angle':23,'heart_opacity':1 if name=='love' else 0})
        if name=='tongue':p['rig'][side+'_highlight'].update({'rx':13,'ry':15})
        small=np.asarray(d['highlight'][j])+[42,35]
        put(side+'_secondary_highlight',[small]);p['rig'][side+'_secondary_highlight'].update({'rx':6 if name=='tense' else 1.5,'ry':9 if name=='tense' else 2,'angle':10,'opacity':1 if name in ('tense','cheeky') else 0})
        if 'under' in d:put(side+'_under_eye',d['under'][j] if j==0 else d['under'][j][::-1],[.3,6,.3])
        else:put(side+'_under_eye',lower+[[0,25],[0,25],[0,25]],[.3,6,.3],0)
        if name not in ('smile','tongue','skeptical'):p['rig'][side+'_under_eye']['opacity']=0
        h1=np.array([518,559]) if j==0 else np.array([1026,474]);h2=np.array([337,606]) if j==0 else np.array([1198,457])
        if name=='love':
            h1,h2=(np.array([480,570]),np.array([342,600])) if j==0 else (np.array([1079,458]),np.array([1213,452]))
        if name=='cheeky':
            h1,h2=(np.array([515,552]),np.array([339,583])) if j==0 else (np.array([1020,466]),np.array([1188,430]))
        if name=='tongue':h1=np.array([505,495]);h2=np.array([330,534]);h2r=np.array([1181,454]);h1r=np.array([1017,469]);h1,h2=(h1,h2) if j==0 else (h1r,h2r)
        if name=='skeptical':h1=np.array([507,520]);h2=np.array([331,537]);h1,h2=(h1,h2) if j==0 else (np.array([1015,502]),np.array([1189,492]))
        put(side+'_hatching',[h1,h2]);p['rig'][side+'_hatching'].update({'count':4 if name=='love' else (6 if name=='cheeky' and j==0 else 5),'length':50,'angle':-52,'width':5,'offsets':[[0,0,1] for _ in range(8)],'opacity':0 if name=='smile' else 1})
        for c,arr in [('lid_accent_inner','inner_accent'),('lid_accent_outer','outer_accent'),('brow_accent','brow_accent')]:
            put(side+'_'+c,d[('outer_accent' if arr=='inner_accent' else 'inner_accent') if j==1 and arr in ('inner_accent','outer_accent') else arr][j],[.3,7 if 'lid' in c else 10,.3],0 if (name not in ('smile','tense') and j==0 and c=='brow_accent') or (name=='tongue' and c=='brow_accent') else 1)
        put(side+'_moustache',d['moustache'][j],[1,44,38,24,22,17,12,1])
        p['variants'][side+'_under_eye']='continuous' if name=='smile' else ('mixed' if name in ('tongue','skeptical') else 'hatching')
        p['variants'][side+'_highlight']='heart' if name=='love' else 'round'
    put('nose',d['nose'],[13,22,5])
    put('mouth_upper',d['mouth'],[6,12,13,12,5]);p['rig']['mouth_upper'].update({'fill_opacity':1 if name in ('tense','love','tongue') else 0,'corner_accent':([0,1] if name in ('smile','cheeky') else ([1,1] if name in ('tongue','skeptical') else [0,0])),'corner_width':8,'corner_size':25})
    a=np.asarray(d['mouth']);lower=d.get('mouth_lower',[a[1].tolist(),a[2].tolist(),a[3].tolist()])
    put('mouth_lower',lower,[7,9,7],1 if name in ('tense','love','tongue') else 0)
    tongue=[[728,719],[752,748],[795,761],[828,744],[847,709]] if name=='love' else [[728,615],[774,750],[845,797],[933,723],[853,592]]
    tongue.append([798,699] if name=='love' else [790,605])
    put('tongue',tongue,opacity=1 if name in ('love','tongue') else 0)
    p['rig']['tongue'].update({'width':9,'fill':'white'})
    put('tongue_crease',[[868,714]],opacity=1 if name=='tongue' else 0);p['rig']['tongue_crease'].update({'width':6,'bend':22})
    put('chin',[[738,699],[770,705],[804,697]],[1,7,1],1 if name=='skeptical' else 0)
    p['variants']['mouth_interior']='white' if name=='tense' else 'dark'
    return refresh_states(p)
