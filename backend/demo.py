from __future__ import annotations
import random, math
from datetime import datetime, timezone
from .metrics import compute_derived, data_confidence

def _months(start_y=2022,start_m=10,n=48):
    y,m=start_y,start_m
    for _ in range(n):
        yield f'{y:04d}-{m:02d}'; m+=1
        if m==13: y+=1; m=1

def seed_demo(store) -> int:
    if store.get('regions','DEMO_CW'):
        return 0
    rng=random.Random(20261005)
    regs=[
      {'id':'DEMO_CW','name':'데모 창원동','full_name':'경상남도 창원시 데모 창원동','sigungu':'창원시','peer_group':'urban','neighbors':['DEMO_KH'],'is_demo':True},
      {'id':'DEMO_KH','name':'데모 김해동','full_name':'경상남도 김해시 데모 김해동','sigungu':'김해시','peer_group':'urban','neighbors':['DEMO_CW'],'is_demo':True},
      {'id':'DEMO_GC','name':'데모 거창읍','full_name':'경상남도 거창군 데모 거창읍','sigungu':'거창군','peer_group':'rural','neighbors':[],'is_demo':True},]
    for r in regs: store.set('regions',r['id'],r,merge=False)
    count=0
    for ri,r in enumerate(regs):
        prev={}; history=[]
        for i,month in enumerate(_months()):
            pop=int((42000 if ri<2 else 18000)*(1-0.0015*i)+350*math.sin(i/5+ri)+rng.randint(-80,80))
            households=int(pop/(2.05 if ri<2 else 1.9)+i*12)
            sale_count=max(1,int((45 if ri<2 else 8)+12*math.sin(i/4+ri)+rng.randint(-5,5)))
            price=int((4_100_000 if ri==0 else 3_500_000 if ri==1 else 2_100_000)*(1+0.002*i)+rng.randint(-100000,100000))
            biz=max(50,int((1500 if ri<2 else 420)*(1+0.001*i)+rng.randint(-15,15)))
            m={'population_total':pop,'households':households,'age_20_39':int(pop*(0.24-0.0004*i if ri<2 else 0.16-0.0003*i)),'age_65_plus':int(pop*(0.17+0.0006*i if ri<2 else 0.28+0.0008*i)),'single_households':int(households*(0.39+0.0006*i)),'one_person_households':int(households*0.39),'two_person_households':int(households*0.28),'apartment_units':int(households*(0.82 if ri<2 else 0.35)),'building_count':5000 if ri<2 else 4200,'old_buildings_30y':int((5000 if ri<2 else 4200)*(0.28+0.002*i)),'sale_count':sale_count,'sale_price_per_m2':price,'rent_count':max(1,int(sale_count*1.8)),'monthly_rent_count':max(1,int(sale_count*0.8)),'jeonse_price':int(price*0.67),'business_count':biz,'business_category_counts':{'food':int(biz*.34),'retail':int(biz*.25),'service':int(biz*.22),'health':int(biz*.08),'education':int(biz*.07),'other':int(biz*.04)}}
            yearago=history[-12] if len(history)>=12 else {}
            d=compute_derived(m,prev,yearago)
            idx={'vitality_index':round(50+(d.get('young_population_share') or 0)/3+(d.get('business_net_change') or 0)/5,2),'housing_pressure_index':round(50+(d.get('sale_price_yoy_pct') or 0)*2,2) if d.get('sale_price_yoy_pct') is not None else 50,'living_convenience_index':round(min(100,40+(d.get('businesses_per_1000_people') or 0)),2),'commerce_change_index':round(50+(d.get('business_net_change') or 0)/2,2)}
            row={'region_id':r['id'],'month':month,'metrics':m,'derived':d,'indexes':idx,'freshness':{'source_as_of':month+'-28','fetched_at':datetime.now(timezone.utc).isoformat(),'is_provisional':False,'sample_size':sale_count,'data_confidence':data_confidence(sale_count),'is_demo':True}}
            store.set('monthly_data',f"{r['id']}_{month}",row,merge=False); store.set('region_latest',r['id'],row,merge=False); prev=m; history.append(m); count+=1
    return count
