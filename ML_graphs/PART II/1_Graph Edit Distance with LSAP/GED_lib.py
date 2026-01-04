#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Oct 20 11:35:26 2022

@author: aldomoscatelli
"""

import networkx as nx
import glob
import matplotlib.pyplot as plt
import numpy as np
import random
import os
import json


def graph_loader(path):
    graph_list = []
    for g in sorted(glob.glob(os.path.join(path, "*.json"))):
        graph_list.append(json.load(open(g)))
    dic_graph = {}
    for k in graph_list:
        G = nx.Graph()
        nodes = k['nodes']
        for n in nodes:
            G.add_node(n['id'],node_label = n['node_label'])
        edges = k['links']
        for e in edges:
            G.add_edge(e['source'],e['target'],edge_label=e['edge_label'])
        dic_graph['g'+str(graph_list.index(k))]=G
    return dic_graph


def draw_pair_graph(graph1,graph2, weight="distance_l2"):
    label1 = {k:lab['node_label']+' '+str(k) for k,lab in graph1.nodes(data=True)}
    label2 = {k:lab['node_label']+' '+str(k) for k,lab in graph2.nodes(data=True)}
    
    subset_color = [
    "red", #carbone
    "yellow", #azote
    "lightblue"] #oxygène
    dic = {'C' :0, 'N':1, 'O':2} 
    
    subset_color_edge = [
    "blue", #simple liaison
    "black", #double liaison
    "darkorange"] #triple liaison
    
    fig, (ax1,ax2) = plt.subplots(1, 2, figsize=(14, 6))
    
    color = [subset_color[dic[data['node_label']]] for v, data in graph1.nodes(data=True)]
    color_edge = [subset_color_edge[data['edge_label']-1] for n1,n2, data in graph1.edges(data=True)]
    position = nx.spring_layout(graph1, weight=weight)

    nx.draw_networkx_nodes(graph1, position, node_color=color, alpha = 1, ax=ax1)
    nx.draw_networkx_edges(graph1, position, edge_color=color_edge,width=4, alpha =1 , ax=ax1)
    nx.draw_networkx_labels(graph1, position, label1, font_size=16, ax=ax1)
    
    color = [subset_color[dic[data['node_label']]] for v, data in graph2.nodes(data=True)]
    color_edge = [subset_color_edge[data['edge_label']-1] for n1,n2, data in graph2.edges(data=True)]
    position = nx.spring_layout(graph2, weight=weight)
    
    nx.draw_networkx_nodes(graph2, position, node_color=color, alpha = 1, ax=ax2)
    nx.draw_networkx_edges(graph2, position, edge_color=color_edge,width=4, alpha =1 , ax=ax2)
    nx.draw_networkx_labels(graph2, position, label2, font_size=16, ax=ax2)
    return ax1,ax2


def edge_weight(tree,node,g1,g2,cost):
    res = 0
    match = tree.nodes(data=True)[node]['label'][0]
    ancestor = tree.nodes(data=True)[node]['label'][1][1:]
    #suppression d'un sommet dans l'arbre
    if -1 in match:
        res += cost['n_del']
        for n in g1.neighbors(match[0]):
            if n+1 > len(ancestor):
                res += cost['e_del']
            else :
                if ancestor[n] != -1 :
                    res += cost['e_del']
    #substitution de sommet dans l'arbre  
    else:
        if g1.nodes()[match[0]]['node_label'] != g2.nodes()[match[1]]['node_label']:
            res += cost['n_sub']
        for n in g1.neighbors(match[0]):
            if n+1 < len(ancestor):
                if ancestor[n] in g2.neighbors(match[1]):
                    if g1.edges[n,match[0]]['edge_label'] != g2.edges[ancestor[n],match[1]]['edge_label']:
                        if cost['e_sub'] < cost['e_del'] + cost['e_ins']:
                            res += cost['e_sub']
                        else:
                            res += cost['e_del'] + cost['e_ins']
                else:
                    if ancestor[n] != -1:
                        res += cost['e_del']
        for n in g2.neighbors(match[1]):
            for i in range(len(ancestor)):
                if n == ancestor[i]:
                    if i not in g1.neighbors(match[0]):
                        res += cost['e_ins']
    # insertion induite des éléments manquants
    if len(ancestor) == len(g1.nodes()): #on est dans une feuille
        matched = [ancestor[i] for i in np.where(np.array(ancestor) != -1)[0]]
        s = len(matched)
        if s != len(g2.nodes()):
            for i in range(len(g2.nodes())):
                if i not in matched:
                    res += cost['n_ins']
                    for n in g2.neighbors(i):
                        if n in matched:
                            res+=cost['e_ins']
                    matched.append(i)
    return res


def hierarchy_pos(G, root=None, width=1., vert_gap = 0.2, vert_loc = 0, xcenter = 0.5):
    if not nx.is_tree(G):
        raise TypeError('cannot use hierarchy_pos on a graph that is not a tree')

    if root is None:
        if isinstance(G, nx.DiGraph):
            root = next(iter(nx.topological_sort(G))) 
        else:
            root = random.choice(list(G.nodes))
            
    def _hierarchy_pos(G, root, width=1., vert_gap = 0.2, vert_loc = 0, xcenter = 0.5, pos = None, parent = None):
        
        if pos is None:
            pos = {root:(xcenter,vert_loc)}
        else:
            pos[root] = (xcenter, vert_loc)
        children = list(G.neighbors(root))
        if not isinstance(G, nx.DiGraph) and parent is not None:
            children.remove(parent)  
        if len(children)!=0:
            dx = width/len(children) 
            nextx = xcenter - width/2 - dx/2
            for child in children:
                nextx += dx
                pos = _hierarchy_pos(G,child, width = dx, vert_gap = vert_gap, 
                                    vert_loc = vert_loc-vert_gap, xcenter=nextx,
                                    pos=pos, parent = root)
        return pos
    
    return _hierarchy_pos(G, root, width, vert_gap, vert_loc, xcenter)

def make_pair_tree(graph1,graph2,cost):
    g1 = graph1
    g2 = graph2
    l1 = len(g1.nodes())
    l2 = len(g2.nodes())
    tree = nx.Graph()
    tree.add_node(0,label=[(-1,-1),[-1]])
    # parcour génératif à mémoire d'ancètre
    # inititalisation
    file = []
    curr = 0
    file.append(curr)
    count = 0
    lvl = 0
    # parcour

    while file and lvl < l1:
        curr = file.pop(0)
        for i in range(l2+1):
            if i == l2:
                count += 1
                lvl = len(tree.nodes()[curr]['label'][-1])-1
                if lvl < l1 :
                    tree.add_node(count,label= [(lvl,-1),tree.nodes()[curr]['label'][-1].copy()])
                    tree.nodes()[count]['label'][-1].append(-1)
                    file.append(count)
                    c = edge_weight(tree,count,g1,g2,cost)
                    tree.add_edge(count,curr,weight=c)
            elif i not in tree.nodes()[curr]['label'][-1]:
                count += 1
                lvl = len(tree.nodes()[curr]['label'][-1])-1
                if lvl < l1 :
                    tree.add_node(count,label= [(lvl,i),tree.nodes()[curr]['label'][-1].copy()])
                    tree.nodes()[count]['label'][-1].append(i)
                    file.append(count)
                    c = edge_weight(tree,count,g1,g2,cost)
                    tree.add_edge(count,curr,weight=c)
    return tree

def count_tree_nodes(N1,N2):
    n1 = N1
    n2 = N2
    u_old=1
    u_new=0
    v_old=0
    v_new=0
    tot=1
    for i in range(n1):
        u_new=u_old*(n2-i)+v_old*n2
        v_new=u_old+v_old
        tot+=(u_new+v_new)
        u_old=u_new
        v_old=v_new
    return tot,(u_new+v_new)

def draw_tree(tree):
    label = {k:lab['label'][0] for k,lab in tree.nodes(data=True)}
    #e_label = {p:lab['weight'] for p,f,lab in tree.edges(data=True)}
    fig, ax = plt.subplots(1, 1, figsize=(40, 10))
    pos = hierarchy_pos(tree,0)
    nx.draw_networkx_nodes(tree, pos,alpha=0.3, ax=ax)
    nx.draw_networkx_edges(tree, pos,alpha=0.3, ax=ax)
    nx.draw_networkx_labels(tree, pos, label, font_size=7, ax=ax)
    edge_labels = nx.get_edge_attributes(tree, "weight")
    nx.draw_networkx_edge_labels(tree, pos, edge_labels, font_size=8, ax=ax)
    return ax

def Dijkstra(tree):
    #init
    P = np.zeros(len(tree.nodes()))
    d = 100000*np.ones(len(tree.nodes()))
    d[0]=0
    sommet = -1
    Q = [i for i in tree.nodes()]
    while Q:
        # choix du sommet courant
        mini = 10000
        for s in Q:
            if d[s]<mini:
                mini = d[s]
                sommet = s
        Q.pop(Q.index(sommet))
        #visite des voisins
        for n in tree.neighbors(sommet):
            if d[n]>d[sommet]+tree.edges[sommet,n]['weight']:
                d[n] = d[sommet]+tree.edges[sommet,n]['weight']
                P[n]=sommet
    return(d,np.array(P).astype('uint'))  

def path(target,P):
    A = []
    s = target
    while s != 0 :
        A.append(s)
        s = P[s]
    A.append(0)
    return A

def path_Dijkstra(tree,g1,g2):
    d,P = Dijkstra(tree)
    N1 = len(g1.nodes())
    N2 = len(g2.nodes())
    tot,leaf = count_tree_nodes(N1,N2)
    d_leaf = d[tot - leaf:]
    target = tot - leaf + np.argmin(d_leaf)
    GED = np.min(d_leaf)
    ged_path = path(target,P)
    return GED,ged_path

def draw_path(tree,ged_path):
    label = {k:lab['label'][0] for k,lab in tree.nodes(data=True)}
    #e_label = {p:lab['weight'] for p,f,lab in tree.edges(data=True)}
    
    subset_color_edge = [
    "lightblue", #arc standard
    "red"]#path
    color_edge = [subset_color_edge[n1 in ged_path and n2 in ged_path] for n1,n2, data in tree.edges(data=True)]
    fig, ax = plt.subplots(1, 1, figsize=(40, 10))
    pos = hierarchy_pos(tree,0)
    nx.draw_networkx_nodes(tree, pos,alpha=0.3, ax=ax)
    nx.draw_networkx_edges(tree, pos,alpha=0.3, ax=ax, edge_color=color_edge,width=4)
    nx.draw_networkx_labels(tree, pos, label, font_size=7, ax=ax)
    edge_labels = nx.get_edge_attributes(tree, "weight")
    nx.draw_networkx_edge_labels(tree, pos, edge_labels, font_size=8, ax=ax)
    return ax

def from_leaf_to_path(tree,leafpath,g1,g2):
    path = []
    for idx in reversed(leafpath):
        path.append(tree.nodes()[idx]['label'][0])
    source = set(i[0] for i in path)
    target = set(i[1] for i in path)
    if set(g1).intersection(source)!=set(g1):
        remaining = set(g1) - set(g1).intersection(source)
        for v in remaining:
            path.append((v,-1))
    if set(g2).intersection(target)!=set(g2):
        remaining = set(g2) - set(g2).intersection(target)
        for v in remaining:
            path.append((-1,v))
    path.remove((-1,-1))
    return path
