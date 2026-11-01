import csv,glob,os,time,statistics,sys
import numpy as np
from sklearn.tree import DecisionTreeRegressor
from sklearn.model_selection import StratifiedKFold
X=[];y=[];cats=[]; overhead=[]
for fn in sorted(glob.glob(os.path.join(sys.argv[1], '*/measurements.csv'))):
 rows=list(csv.DictReader(open(fn))); category=os.path.basename(os.path.dirname(fn))
 for name in sorted({r['formula'] for r in rows}):
  path=os.path.join(os.path.dirname(fn),name); start=time.perf_counter(); n=m=pos=neg=binary=ternary=0
  with open(path) as f:
   for line in f:
    if line.startswith('p '): _,_,n,m=line.split(); n=int(n);m=int(m)
    elif line and line[0] not in 'c%\n':
     a=[int(x) for x in line.split() if int(x)!=0];binary+=len(a)==2;ternary+=len(a)==3;pos+=sum(x>0 for x in a);neg+=sum(x<0 for x in a)
  overhead.append(time.perf_counter()-start)
  d={mode:statistics.median(float(r['par2_s']) for r in rows if r['formula']==name and r['mode']==mode) for mode in ('monitor','stable_v1531')}
  X.append([n,m/max(n,1),binary/max(m,1),ternary/max(m,1),pos/max(pos+neg,1)]);y.append((d['monitor']-d['stable_v1531'])/max(d['monitor'],1e-9));cats.append(category)
X=np.array(X); y=np.array(y);cats=np.array(cats);o=np.array(overhead)
pred=np.zeros(len(y));cv=StratifiedKFold(n_splits=5,shuffle=True,random_state=20261101)
for tr,te in cv.split(X,cats):
 model=DecisionTreeRegressor(max_depth=2,min_samples_leaf=8,random_state=42);model.fit(X[tr],y[tr]);pred[te]=model.predict(X[te])
choose=pred>0.1
print('cases',len(y),'selected',sum(choose),'mean estimated percentage gain excluding feature cost',100*np.mean(np.where(choose,y,0)),'median',100*np.median(np.where(choose,y,0)))
print('mean feature extraction ms',1000*np.mean(o),'median',1000*np.median(o));print('category selected',[(c,int(sum(choose[cats==c])),round(100*np.mean(np.where(choose[cats==c],y[cats==c],0)),3)) for c in sorted(set(cats))])
from sklearn.tree import export_text
model=DecisionTreeRegressor(max_depth=2,min_samples_leaf=8,random_state=42).fit(X,y)
print(export_text(model,feature_names=['vars','density','binary_fraction','ternary_fraction','positive_fraction']))
print('tree feature',model.tree_.feature.tolist(),'thresholds',model.tree_.threshold.tolist())
