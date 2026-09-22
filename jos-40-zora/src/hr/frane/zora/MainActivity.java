package hr.frane.zora;

import android.app.Activity;
import android.os.Bundle;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.ActivityInfo;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Shader;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import java.util.ArrayList;
import java.util.Random;

public class MainActivity extends Activity {
    Game game;
    @Override public void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN,WindowManager.LayoutParams.FLAG_FULLSCREEN);
        getWindow().getDecorView().setSystemUiVisibility(5894|1024|512);
        setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE);
        game = new Game(this);
        setContentView(game);
    }
    @Override protected void onPause() {
        super.onPause();
        if(game!=null) game.save();
    }

    final class Game extends View {
        final Paint p=new Paint(3);
        final Random rng=new Random();
        final SharedPreferences pref;
        final ArrayList<Btn> buttons=new ArrayList<>();
        int day=1, scene=0, food=1, wire=0, hunger=65, petHunger=54, clean=68, mood=51, bond=15, order=64, karma=0, actions=5, playerX=380, move=0, event=-1, searches=0;
        boolean trap=false, lizard=false, finished=false;
        String story="Zadnja limenka. Vani je tisina. Trebat ce nam zamka.";
        String subtitle="DAN 1  /  TUTORIJAL";
        long start=System.currentTimeMillis();
        float vw=960,vh=540;
        final String[] eventTitles={
            "Stranac pred vratima", "Napusteno skloniste", "Stara fotografija",
            "Ranjen mali stvor", "Nocni radio", "Neocekivana oluja",
            "Posljednje sjeme", "Svitanje cetrdesetog dana"
        };
        final String[] eventTexts={
            "Netko kuca. Trazi vodu i malo hrane. Hoce li bunker ostati otvoren?",
            "U prasini nalazis paket. Na njemu pise: ZA ONOGA KOME TREBA.",
            "Slika obitelji. Mogao bi je sacuvati ili je baciti u vatru.",
            "Uz stazu lezi zivotinja. Pomoc zahtijeva dio tvojih zaliha.",
            "Radio hvata glas koji poziva prezivjele na zajednistvo.",
            "Vjetar nosi smece. Mozes spasiti gusterovo skroviste ili zalihe.",
            "Jedno sjeme. Posaditi ga ili pojesti prije novog dana?",
            "Na horizontu se vide svjetla. Krenuti zajedno ili ostati sam?"
        };
        final String[] yes={"Podijeli hranu","Ostavi paket","Sacuvaj sliku","Pomogni","Odgovori","Spasi gusterovo mjesto","Posadi sjeme","Kreni zajedno"};
        final String[] no={"Zatvori vrata","Uzmi sve","Spali sliku","Produzi dalje","Ugasi radio","Spasi zalihe","Pojedi sjeme","Ostani u bunkeru"};
        class Btn {
            final float x,y,w,h; final String id;
            Btn(float a,float b,float c,float d,String s){x=a;y=b;w=c;h=d;id=s;}
            boolean hit(float tx,float ty){return tx>=x&&tx<=x+w&&ty>=y&&ty<=y+h;}
        }
        Game(Context ctx){super(ctx);pref=ctx.getSharedPreferences("zora-save-v1",0);load();setLayerType(View.LAYER_TYPE_SOFTWARE,null);}
        void load(){
            day=pref.getInt("day",1);scene=pref.getInt("scene",0);food=pref.getInt("food",1);
            wire=pref.getInt("wire",0);hunger=pref.getInt("hunger",65);petHunger=pref.getInt("petHunger",54);
            clean=pref.getInt("clean",68);mood=pref.getInt("mood",51);bond=pref.getInt("bond",15);
            order=pref.getInt("order",64);karma=pref.getInt("karma",0);actions=pref.getInt("actions",5);
            playerX=pref.getInt("playerX",380);event=pref.getInt("event",-1);
            searches=pref.getInt("searches",0);trap=pref.getBoolean("trap",false);
            lizard=pref.getBoolean("lizard",false);finished=pref.getBoolean("finished",false);
            story=pref.getString("story",story);subtitle=pref.getString("subtitle",subtitle);
        }
        void save(){
            pref.edit().putInt("day",day).putInt("scene",scene).putInt("food",food)
            .putInt("wire",wire).putInt("hunger",hunger).putInt("petHunger",petHunger)
            .putInt("clean",clean).putInt("mood",mood).putInt("bond",bond).putInt("order",order)
            .putInt("karma",karma).putInt("actions",actions).putInt("playerX",playerX)
            .putInt("event",event).putInt("searches",searches).putBoolean("trap",trap)
            .putBoolean("lizard",lizard).putBoolean("finished",finished)
            .putString("story",story).putString("subtitle",subtitle).apply();
        }
        int cap(int v){return Math.max(0,Math.min(100,v));}
        void msg(String s){story=s;save();invalidate();}
        void act(String a){
            if(a.equals("L")||a.equals("R")){move=a.equals("L")?-1:1;return;}
            if(finished){if(a.equals("RESTART"))reset();return;}
            if(event>=0){if(a.equals("YES")||a.equals("NO"))choose(a.equals("YES"));return;}
            if(a.equals("OUT")){
                scene=1;subtitle=day==1&&!lizard?"DAN 1 / POTRAGA ZA ZICOM":"VANJSKI SVIJET";
                msg("Sloj pepela skriva tragove. Pomakni se i pretrazi okolinu.");return;
            }
            if(a.equals("IN")){
                if(day==1&&!lizard){
                    if(!trap){msg("Prvo postavi zamku. Zica i otpad su negdje vani.");return;}
                    lizard=true;scene=0;subtitle="DAN 1 / NEPOZVANI GOST";
                    msg("Vrata su ostala otvorena! U bunkeru je neobicni mali guster. Gleda te i ne bjezi.");
                } else {scene=0;subtitle="BUNKER / SIGURNA ZONA";msg("Vracas se u bunker. Guster te prepoznaje.");}
                return;
            }
            if(a.equals("SEARCH")){
                if(actions<=0){msg("Umoran si. Vrati se i odmori.");return;}
                actions--;searches++;
                if(wire==0&&!trap){wire=1;food++;msg("Ispod hrpe smeca pronalazis zicu i konzervu! Sada mozes postaviti zamku.");}
                else {int found=1+(searches%3==0?1:0); food+=found;if(searches%2==0)wire++;
                    msg("U sutu nalazis "+found+" obrok(a)"+(searches%2==0?" i zicu.":".")+" Praznina je ipak nesto dala.");}
                clean=cap(clean-3);save();return;
            }
            if(a.equals("TRAP")){
                if(trap){msg("Zamka je vec tu. Pregledat ces je sutra.");return;}
                if(wire<1){msg("Nemas zice. Pretrazi grmlje i smece.");return;}
                if(actions<1){msg("Nemoguce je namjestiti zamku bez snage.");return;}
                wire--;actions--;trap=true;msg("Zica je napeta. Zamka je spremna. Vrati se do bunkera.");return;
            }
            if(!lizard){msg("Nesto ti nedostaje. Izadi van po materijal.");return;}
            if(a.equals("FEEDPET")){
                if(food<1){msg("Nema hrane. Mozes je potraziti vani.");return;}
                if(actions<1){msg("Treba ti san prije novih poslova.");return;}
                food--;actions--;petHunger=cap(petHunger+35);bond=cap(bond+5);mood=cap(mood+5);
                msg("Mali guster polako prilazi i uzima hranu iz tvoje ruke.");return;
            }
            if(a.equals("FEEDME")){
                if(food<1){msg("Limenke su prazne. Treba opet u potragu.");return;}
                food--;hunger=cap(hunger+43);msg("Pojeden je jedan obrok. Snaga se polako vraca.");return;
            }
            if(a.equals("CLEAN")){
                if(actions<1){msg("Nemozes vise, dan je bio dug.");return;}
                actions--;clean=cap(clean+25);order=cap(order+20);petHunger=cap(petHunger-2);
                msg("Oprana je posuda i slozene police. I guster lakse dise.");return;
            }
            if(a.equals("TALK")){
                if(actions<1){msg("Preumoran si za razgovor.");return;}
                actions--;mood=cap(mood+19);bond=cap(bond+13);
                String[] lines={"Guster tiho podize glavu. Cini se da razumije.",
                  "Guster je zaspao na rubu tvog rukava.","Prvi put cujes neobican zvuk, gotovo kao rijec.",
                  "U ovom bunkeru vise nitko nije sasvim sam."};
                msg(lines[Math.min(3,(day-1)/10)]);return;
            }
            if(a.equals("SLEEP"))nextDay();
        }
        void choose(boolean good){
            int current=event;event=-1;
            if(good){karma+=2;bond=cap(bond+6);mood=cap(mood+7);if(current==0||current==3)food=Math.max(0,food-1);
                msg("Izabrao si brigu za drugoga. Nista se ne zaboravlja.");}
            else {karma-=1;food+=(current==1||current==5||current==6)?2:0;
                mood=cap(mood-5);msg("Odabrao si cuvati svoje. Bunker je utihnuo.");}
            if(day==40){finished=true;scene=0;msg(ending());}
            save();
        }
        String ending(){
            if(bond>=60&&karma>=6&&petHunger>15&&hunger>15)
                return "KRAJ: NOVO JUTRO. Izlazite zajedno. Ono sto ste sacuvali u mraku vodi vas prema svjetlu.";
            if(bond>=35&&hunger>0&&petHunger>0)
                return "KRAJ: DVOJE PREZIVJELIH. Bunker ostaje dom, ali vrata vise nisu zakljucana.";
            return "KRAJ: TIHI BUNKER. Prezivjeli ste oluju, ali svijet ceka drugaciji pocetak.";
        }
        void nextDay(){
            if(scene!=0){msg("Za spavanje moras biti u bunkeru.");return;}
            if(day==1&&!lizard){msg("Prvo zavrsi tutorijal i upoznaj gosta.");return;}
            if(day>=40){finished=true;msg(ending());return;}
            day++;actions=5;searches=0;hunger=cap(hunger-15);petHunger=cap(petHunger-13);
            clean=cap(clean-9);order=cap(order-7);mood=cap(mood-5);
            if(trap)food+=1+(day%4==0?1:0);
            if(hunger==0)mood=cap(mood-8);
            if(petHunger==0)bond=cap(bond-6);
            if(clean<20)mood=cap(mood-8);
            subtitle="DAN "+day+" / JOS "+(40-day)+" ZORA";
            if(day%10==0){msg("Novi dan. Guster je porastao! Njegove oci sve vise razumiju svijet.");}
            else msg("Novo jutro. Zamka je "+(trap?"donijela hranu.":"prazna.")+" Zalihe: "+food+".");
            if(day%5==0){event=day/5-1;save();}
        }
        void reset(){
            pref.edit().clear().commit();
            day=1;scene=0;food=1;wire=0;hunger=65;petHunger=54;clean=68;mood=51;bond=15;
            order=64;karma=0;actions=5;playerX=380;move=0;event=-1;searches=0;trap=false;lizard=false;finished=false;
            story="Zadnja limenka. Vani je tisina. Trebat ce nam zamka.";
            subtitle="DAN 1 / TUTORIJAL";save();
        }
        void rect(Canvas c,int color,float x,float y,float w,float h){
            p.setShader(null);p.setStyle(Paint.Style.FILL);p.setColor(color);c.drawRect(x,y,x+w,y+h,p);
        }
        void rr(Canvas c,int color,float x,float y,float w,float h,float r){
            p.setShader(null);p.setStyle(Paint.Style.FILL);p.setColor(color);
            c.drawRoundRect(x,y,x+w,y+h,r,r,p);
        }
        void oval(Canvas c,int color,float x,float y,float w,float h){
            p.setShader(null);p.setColor(color);p.setStyle(Paint.Style.FILL);c.drawOval(x,y,x+w,y+h,p);
        }
        void line(Canvas c,int color,float x,float y,float xx,float yy,float width){
            p.setShader(null);p.setColor(color);p.setStyle(Paint.Style.STROKE);p.setStrokeWidth(width);
            c.drawLine(x,y,xx,yy,p);p.setStyle(Paint.Style.FILL);
        }
        void txt(Canvas c,String s,float x,float y,int size,int color,boolean bold){
            p.setShader(null);p.setColor(color);p.setTypeface(bold?android.graphics.Typeface.create("sans-serif",1):android.graphics.Typeface.create("sans-serif",0));
            p.setTextSize(size);p.setStyle(Paint.Style.FILL);c.drawText(s,x,y,p);
        }
        void paragraph(Canvas c,String s,int x,int y,int width,int size,int color){
            String[] words=s.split(" ");String t="";int pos=y;
            for(String w:words){
                String next=t.length()==0?w:t+" "+w;
                p.setTextSize(size);
                if(p.measureText(next)>width&&!t.isEmpty()){
                    txt(c,t,x,pos,size,color,false);pos+=size+6;t=w;
                }else t=next;
            }
            if(!t.isEmpty())txt(c,t,x,pos,size,color,false);
        }
        void button(Canvas c,String id,String caption,int x,int y,int w,int h,int color){
            rr(c,0x88000000,x+3,y+4,w,h,11);
            rr(c,color,x,y,w,h,11);rr(c,0x18ffffff,x+3,y+3,w-6,h/2,8);
            p.setTextSize(18);p.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
            txt(c,caption,x+(w-p.measureText(caption))/2,y+h/2+6,18,Color.WHITE,true);
            buttons.add(new Btn(x,y,w,h,id));
        }
        void sky(Canvas c,float t){
            p.setShader(new LinearGradient(0,0,0,420,new int[]{0xff101b30,0xff4a4659,0xffa57b66},null,Shader.TileMode.CLAMP));
            c.drawRect(0,0,960,540,p);p.setShader(null);
            int sunX=740+(int)(Math.sin(day*0.25)*75);
            oval(c,0x3388deef,sunX-32,60,130,130);
            oval(c,0xffffc98d,sunX,90,66,66);
            for(int layer=0;layer<3;layer++){
                int color=new int[]{0xff394457,0xff303b45,0xff26333b}[layer];
                Path path=new Path();path.moveTo(0,400);
                for(int x=0;x<=1020;x+=35)
                    path.lineTo(x,245+layer*54+(float)Math.sin(x*.011+layer*2.7+playerX*.0008*(layer+1))*44);
                path.lineTo(960,540);path.lineTo(0,540);path.close();
                p.setColor(color);c.drawPath(path,p);
            }
            for(int i=0;i<24;i++){
                int x=(i*157+20-(playerX*(i%3+1)/8))%1040;
                if(x<0)x+=1040;
                line(c,0x385a483e,x,386+(i%5)*11,x+3,349+(i%7)*4,1);
            }
        }
        void outside(Canvas c,float t){
            sky(c,t);
            rect(c,0xff493c35,0,421,960,119);
            for(int i=0;i<49;i++){
                int x=(i*83+37-playerX/4)%1030;if(x<0)x+=1030;
                line(c,0xff84715b,x,427+(i%5)*13,x+4,420+(i%4)*13,2);
            }
            // The sealed bunker provides a fixed anchor in the scrolling world.
            rr(c,0xff181f26,36,281,208,158,10);
            rr(c,0xff45535a,64,304,154,131,9);
            rr(c,0xff151c24,91,328,95,107,8);
            line(c,0xff9b9b83,100,350,178,350,4);
            oval(c,0xffd8a160,163,371,6,6);
            for(int i=0;i<10;i++){
                int x=340+i*65;int y=426+(i%3)*7;
                oval(c,0xff4a4a43,x,y,30+i%3*10,7);
            }
            // Rusted wreckage and tangled shrubs.
            for(int i=0;i<8;i++){
                int x=315+i*83-playerX/8;
                line(c,0xff2f362f,x,423,x-8,404-i%4*6,3);
                line(c,0xff2f362f,x,423,x+9,405-i%5*5,3);
                if(i%2==0){rr(c,0xff6a5145,x+13,415,22,13,2);line(c,0xff9a7860,x+20,414,x+21,406,2);}
            }
            if(trap){
                line(c,0xffc3aa79,670,426,710,400,3);line(c,0xffc3aa79,710,400,754,426,3);
                line(c,0xffb9ada0,678,420,748,420,2);
                txt(c,"ZAMKA",678,394,12,0xffffdbad,true);
            }
            player(c,playerX,408,t);
            txt(c,"BUNKER",69,296,16,0xffb4c9d0,true);
            txt(c,"OTPAD I ZARASLA STAZA",485,296,18,0xffffd7b2,true);
        }
        void player(Canvas c,int x,int y,float t){
            int step=move==0?0:(int)(Math.sin(t*.013)*6);
            oval(c,0x80000000,x-23,y+11,47,9);
            line(c,0xff1b2731,x-9,y-2,x-13-step,y+13,9);
            line(c,0xff1b2731,x+10,y-2,x+14+step,y+13,9);
            rr(c,0xff404f51,x-16,y-49,32,48,7);
            rr(c,0xffa88969,x-12,y-78,24,28,10);
            rr(c,0xff242e30,x-14,y-82,29,12,4);
            rr(c,0xff7c6551,x+9,y-42,14,29,5);
            line(c,0xffc6ac82,x+13,y-34,x+19,y-15,7);
            oval(c,0xffcddad3,x+4,y-68,4,4);
            rr(c,0xff2d3939,x-25,y-45,12,39,4);
        }
        void bunker(Canvas c,float t){
            rect(c,0xff0e1922,0,0,960,540);
            for(int i=0;i<12;i++){
                rect(c,0xff1a2a32,0,i*37,960,2);
                for(int j=0;j<8;j++)rect(c,0xff243640,j*143+(i%2)*44,i*37,2,36);
            }
            rect(c,0xff3e3933,0,400,960,140);
            p.setShader(new LinearGradient(0,340,0,540,0xff6e5a49,0xff1d2023,Shader.TileMode.CLAMP));
            c.drawRect(0,400,960,540,p);p.setShader(null);
            rr(c,0xff2e424b,45,110,205,288,7);
            rr(c,0xff111e27,63,135,165,236,6);
            for(int i=0;i<4;i++){
                rect(c,0xff6b6658,55,179+i*46,188,8);
                rr(c,0xff8c694c,75,145+i*47,45,34,4);
                rr(c,0xffa4a18b,133,149+i*47,18,28,3);
                rr(c,0xff8b9a9a,169,152+i*47,39,23,2);
            }
            rr(c,0xff39434a,723,130,168,272,5);
            rr(c,0xff121a21,743,156,130,223,5);
            line(c,0xff7b7770,755,198,855,198,7);
            oval(c,0xffa8794a,835,249,9,9);
            rr(c,0xff66564a,287,321,369,94,9);
            rr(c,0xffa38b62,310,314,330,33,5);
            for(int j=0;j<5;j++)line(c,0xff484039,317+j*70,349,317+j*70,415,3);
            oval(c,0xff202627,446,349,153,32);
            player(c,340,408,t);
            if(lizard)lizard(c,515,338,t);
            // flickering hanging lamp and dust
            line(c,0xff202c31,472,0,472,97,4);
            oval(c,0xffb4a17a,432,85,79,27);
            oval(c,0x44ffe0a4,411,93,122,46);
            oval(c,0xffffe4aa,464,97,18,9);
            for(int i=0;i<19;i++){
                float dx=(i*139+t*.007f*(i%3+1))%960;
                float dy=(i*77+t*.014f*(i%2+1))%390+30;
                oval(c,0x447e8d91,dx,dy,2,2);
            }
            txt(c,"SKLONISTE  /  SEKTOR 04",27,92,21,0xffacbbc0,true);
        }
        void lizard(Canvas c,int x,int y,float t){
            int grow=Math.min(3,(day-1)/10);
            float scale=1+grow*.27f;
            c.save();c.translate(x,y);c.scale(scale,scale);
            Path tail=new Path();tail.moveTo(27,7);
            tail.cubicTo(64,4,54,43,93,16);
            p.setStyle(Paint.Style.STROKE);p.setStrokeCap(Paint.Cap.ROUND);
            p.setStrokeWidth(9);p.setColor(0xff65927c);c.drawPath(tail,p);p.setStyle(Paint.Style.FILL);
            oval(c,0xff385951,-36,-5,80,37);
            oval(c,0xff79ac89,-40,-23,75,49);
            oval(c,0xffacd1a2,-30,-15,54,33);
            oval(c,0xff638c77,-47,-42,54,44);
            oval(c,0xff95bc91,-40,-38,45,33);
            oval(c,0xffe5bc82,-25,-27,14,17);
            oval(c,0xff0f2727,-20,-22,7,12);
            oval(c,0xffffffff,-19,-21,3,3);
            line(c,0xff2b5042,-43,5,-53,13,6);
            line(c,0xff2b5042,-5,19,-10,32,7);
            line(c,0xff2b5042,26,15,32,29,7);
            oval(c,0xff223c36,-33,-6,3,3);
            if(day>20){txt(c,"...",-25,-53,11,0xffe5efc0,true);}
            c.restore();
        }
        void bar(Canvas c,String name,int val,int x,int y,int col){
            txt(c,name,x,y-6,13,0xffdee6e4,true);
            rr(c,0xff172029,x,y,127,10,5);
            rr(c,col,x,y,127*cap(val)/100f,10,5);
            txt(c,""+val,x+133,y+10,12,0xfff4eddc,true);
        }
        @Override protected void onDraw(Canvas canvas){
            super.onDraw(canvas);
            canvas.drawColor(Color.BLACK);
            float s=Math.min(getWidth()/960f,getHeight()/540f);
            float offX=(getWidth()-960*s)/2,offY=(getHeight()-540*s)/2;
            canvas.save();canvas.translate(offX,offY);canvas.scale(s,s);
            float t=System.currentTimeMillis()-start;
            buttons.clear();
            if(scene==1)outside(canvas,t);else bunker(canvas,t);
            rr(canvas,0xe5112029,0,0,960,64,0);
            txt(canvas,"JOS 40 ZORA",22,27,23,0xffffd2a1,true);
            txt(canvas,subtitle,23,51,15,0xffb9cece,false);
            txt(canvas,"DAN "+day+" / 40",798,28,20,0xffffd2a1,true);
            txt(canvas,"HRANA "+food+"    ZICA "+wire+"    SNAGA "+actions,713,51,14,0xffe1e4d8,false);
            rr(canvas,0xdc12212a,10,69,178,100,9);
            bar(canvas,"TI",hunger,20,91,0xffc99a68);
            bar(canvas,"GUSTER",petHunger,20,124,0xff7fbc91);
            bar(canvas,"POVEZANOST",bond,20,157,0xffc2a2cb);
            rr(canvas,0xdc12212a,783,70,167,98,9);
            txt(canvas,"CISTOCA "+clean,798,100,15,0xffd9e8e4,true);
            txt(canvas,"RED "+order,798,127,15,0xffd9e8e4,true);
            txt(canvas,"RASP. "+mood,798,154,15,0xffd9e8e4,true);
            if(!finished && event<0){
                rr(canvas,0xef13222b,10,445,940,85,11);
                paragraph(canvas,story,27,469,910,18,0xfff7ead0);
                if(scene==1){
                    button(canvas,"L","◀",19,360,70,69,0xff546a73);
                    button(canvas,"R","▶",97,360,70,69,0xff546a73);
                    button(canvas,"SEARCH","PRETRAZI",210,479,160,42,0xff59715c);
                    button(canvas,"TRAP","ZAMKA",381,479,131,42,0xff7c6b53);
                    button(canvas,"IN","U BUNKER",526,479,163,42,0xff405b76);
                }else if(!lizard){
                    button(canvas,"OUT","IZADI VAN",720,479,214,42,0xff526e64);
                }else{
                    button(canvas,"FEEDME","JEDI",17,479,108,42,0xff847056);
                    button(canvas,"FEEDPET","HRANI",132,479,110,42,0xff597b67);
                    button(canvas,"CLEAN","OCISTI",249,479,111,42,0xff5a747f);
                    button(canvas,"TALK","PRICAJ",367,479,112,42,0xff786883);
                    button(canvas,"OUT","VANI",486,479,94,42,0xff526e64);
                    button(canvas,"SLEEP","NOVI DAN",676,479,263,42,0xff9a764d);
                }
                if(scene==1)txt(canvas,"POMICANJE",25,350,11,0xfff2e8d8,true);
            }
            if(event>=0&&!finished){
                rr(canvas,0xf1101921,170,125,620,320,20);
                txt(canvas,"DOGADAJ  /  DAN "+day,205,169,19,0xffffc48f,true);
                txt(canvas,eventTitles[event],205,212,25,0xffffffff,true);
                paragraph(canvas,eventTexts[event],205,248,535,20,0xffdee4df);
                button(canvas,"YES",yes[event],201,361,252,54,0xff527963);
                button(canvas,"NO",no[event],469,361,281,54,0xff795a54);
            }
            if(finished){
                rr(canvas,0xf00e1b22,110,114,740,328,19);
                txt(canvas,"40 DANA JE PROSLO",155,170,31,0xffffd9aa,true);
                paragraph(canvas,ending(),155,217,630,23,0xffe1ebe5);
                txt(canvas,"POVEZANOST "+bond+"     DOBROTA "+karma,155,330,18,0xffbcd4be,true);
                button(canvas,"RESTART","NOVA IGRA",350,366,263,58,0xff607e72);
            }
            canvas.restore();
            // Perform simple constant-speed horizontal motion while a control is held.
            if(move!=0 && scene==1 && event<0){
                playerX=Math.max(250,Math.min(900,playerX+move*4));
            }
            postInvalidateDelayed(33);
        }
        @Override public boolean onTouchEvent(MotionEvent e){
            float s=Math.min(getWidth()/960f,getHeight()/540f);
            float x=(e.getX()-(getWidth()-960*s)/2)/s;
            float y=(e.getY()-(getHeight()-540*s)/2)/s;
            if(e.getActionMasked()==MotionEvent.ACTION_DOWN){
                for(int i=buttons.size()-1;i>=0;i--){
                    Btn b=buttons.get(i);if(b.hit(x,y)){act(b.id);invalidate();return true;}
                }
                return true;
            }
            if(e.getActionMasked()==MotionEvent.ACTION_UP||e.getActionMasked()==MotionEvent.ACTION_CANCEL){
                move=0;save();return true;
            }
            return true;
        }
    }
}
