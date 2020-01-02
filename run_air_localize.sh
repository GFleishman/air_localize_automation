#!/bin/bash


# the image from which to find spots
image="/groups/multifish/multifish/Yuhan/Stitch/CEA_3_R10/Stitch/n5"
# the folder where you'd like all outputs to be written
outdir="/groups/multifish/multifish/fleishmang/alignments/spots_CEA_3_R10"


# the channel from which to find spots
channel="c0,c1,c3"
# the scale level at which to find spots
scale="s0"
# the number of voxels along x/y for tiling
xy_stride=1024
# the number of voxels to overlap along x/y between tiles
xy_overlap=51
# the number of voxels along z for tiling
z_stride=256
# the number of voxels to overlap along z between tiles
z_overlap=26

# the air localize parameters file
# the numerical parameters related to air localize are found in this file
params="/groups/multifish/multifish/fleishmang/air_localize/air_localize_default_params.txt"


# DO NOT EDIT BELOW THIS LINE
air_localize='/groups/multifish/multifish/fleishmang/air_localize/air_localize.sh'
bash "$air_localize" "$image" "$channel" "$scale" "$xy_stride" \
     "$xy_overlap" "$z_stride" "$z_overlap" "$params" "$outdir"

