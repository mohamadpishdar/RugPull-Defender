"""Figure 1: architecture of the Rug-Pull Defender cascade (writes results/figures/Figure1_architecture.{png,pdf})."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10})
fig,ax=plt.subplots(figsize=(8.2,3.6)); ax.set_xlim(0,100); ax.set_ylim(0,43); ax.axis("off")
C=dict(src="#EEF1F7",w1="#E1F4EC",w2="#E6EEF8",w3="#FBEDE3",gate="#FFF1CC",out="#EEE9F8",edge="#3A3A3A")
def box(x,y,w,h,txt,fc,bold=False,fs=10):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0.25,rounding_size=0.8",fc=fc,ec=C["edge"],lw=1.3))
    ax.text(x+w/2,y+h/2,txt,ha="center",va="center",fontsize=fs,fontweight="bold" if bold else "normal",linespacing=1.25)
    return (x,y,w,h)
def arrow(p,q,lab=None,lp=None,style="-|>",ls="-",col="#3A3A3A"):
    ax.add_patch(FancyArrowPatch(p,q,arrowstyle=style,mutation_scale=13,lw=1.3,color=col,linestyle=ls,shrinkA=0,shrinkB=0))
    if lab: ax.text(*lp,lab,fontsize=8.5,style="italic",ha="center",va="center")
src=box(0.3,16.5,14.2,10,"Smart contract\n(source code\nand bytecode)",C["src"],fs=8.5)
w1=box(22,31,19,9.5,"W1: CodeBERT\nwhole contract in\n512-token windows",C["w1"],fs=8.5)
w2=box(22,16.75,19,9.5,"W2: Forta-style\nlexical rules\n(fixed weights)",C["w2"],fs=8.5)
w3=box(22,2.5,19,9.5,"W3: CRPWarner\nbytecode flags\n(W3$_{lean}$ = 0.8 or 0.2)",C["w3"],fs=8.5)
gate=box(49,15.5,17,12,"Gate:\nW1 in [$\\ell$, $h$]?",C["gate"],bold=True,fs=9)
direct=box(74,29,24.5,10,"Final score = W1",C["w1"],fs=9)
blend=box(74,4,24.5,12,"Final score =\n(W1 + $\\alpha$ W2 + $\\beta$ W3$_{lean}$)\n/ (1 + $\\alpha$ + $\\beta$)",C["w3"],fs=8.5)
# source -> modalities
for (x,y,w,h) in (w1,w2,w3):
    arrow((14.6,21.5),(x-0.5,y+h/2))
# W1 -> gate
arrow((41.5,35.75),(48.5,25.5))
# W2, W3 -> blend (dashed: only used when gate opens)
ax.plot([41.5,45.5],[21.5,13.2],ls="--",color="#7A7A7A",lw=1.3)
arrow((45.5,13.2),(73.5,13.2),ls="--",col="#7A7A7A")
arrow((41.5,7.25),(73.5,8),ls="--",col="#7A7A7A")
# gate outcomes
arrow((66.5,25),(73.5,32),"No",(68.2,30.3))
arrow((66.5,18),(73.5,14.5),"Yes",(70.8,18.4))
ax.text(86.25,22.6,"Either path: rug pull\nif final score $\\geq$ $\\tau$",ha="center",va="center",fontsize=8.5,fontweight="bold",linespacing=1.2)
ax.text(86.25,41.3,"",ha="center")
plt.tight_layout(pad=0.2)
import os
out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results", "figures")
os.makedirs(out, exist_ok=True)
plt.savefig(os.path.join(out, "Figure1_architecture.png"), dpi=300); plt.savefig(os.path.join(out, "Figure1_architecture.pdf"))
