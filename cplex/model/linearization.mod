
int sampleSize=10000;
float s=0;
float e=10;

float x[i in 0..sampleSize]=s+(e-s)*i/sampleSize;

int nbSegments=5;

float x2[i in 0..nbSegments]=(s)+(e-s)*i/nbSegments;
float y2[i in 0..nbSegments]=log(1 + x2[i]);  // y=f(x)

float firstSlope=0;
 float lastSlope=0;
 
 tuple breakpoint // y=f(x)
 {
  key float x;
  float y;
 }
 
 sorted { breakpoint } breakpoints={<x2[i],y2[i]> | i in 0..nbSegments};
 
 float slopesBeforeBreakpoint[b in breakpoints]=
 (b.x==first(breakpoints).x)
 ?firstSlope
 :(b.y-prev(breakpoints,b).y)/(b.x-prev(breakpoints,b).x);
 
 pwlFunction f=piecewise(b in breakpoints)
 { slopesBeforeBreakpoint[b]->b.x; lastSlope } (first(breakpoints).x, first(breakpoints).y);
 
 assert forall(b in breakpoints) abs(f(b.x)-b.y)<=0.001;
 
 float maxError=max (i in 0..sampleSize) abs(1/x[i]-f(x[i]));
 float averageError=1/(sampleSize+1)*sum (i in 0..sampleSize) abs(1/x[i]-f(x[i]));