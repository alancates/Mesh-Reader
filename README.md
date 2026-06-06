# Mesh-Reader

A project workspace for building Mesh-Reader with Perplexity.

## Goal

Read mesh files in viewer cache and save them as OBJ files for import to Blender 5+.

## Current status

Project created. Initial setup in progress.

## How to run

Instructions:
At start of a Perplexity session paste:
  Project: Mesh-Reader
  Goal: Read/save SL mesh cache files as OBJ for Blender
  Last done: [what you finished]
  Working on now: [current task]
  Blocker: [any problem, or "none"]

## Firestorm source leads

Core mesh/model code:
- indra/llprimitive/llmodel.h
- indra/llprimitive/llmodel.cpp
- indra/llprimitive/llmodelloader.h
- indra/llprimitive/llmodelloader.cpp

Reason:
These files define LLModel and LLModelLoader, which appear to be the main mesh/model classes in Firestorm.
