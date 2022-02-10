#!/bin/bash


function get_job_dependency {
  dependencies=$( echo ${1?} | tr "," "\n" )
  for dep in ${dependencies[@]}; do
      bjobs_lines=`bjobs -J "${dep}"`
      jobids=`echo "$bjobs_lines" | cut -f 1 -d' ' | tail -n +2 | uniq`
      for jobid in ${jobids[@]}; do
        dependency_string="${dependency_string}ended($jobid)&&"
      done
  done
  dependency_string=${dependency_string::-2}
  echo $dependency_string
}


function submit {
    name=${1?};       shift
    dependency=${1?}; shift
    cores=${1?};      shift
    execute="$@"

    [[ -z "$dependency" ]] || dependency=$(get_job_dependency $dependency)
    [[ -z "$dependency" ]] || dependency="-w $dependency"

    bsub -J $name \
         -n $cores \
         -o ${logdir}/${name}.o \
         -e ${logdir}/${name}.e \
         -P $BILLING \
         $dependency \
         "$execute"
}


function initialize_environment {
  logdir="${outdir}/logs";    mkdir -p $logdir
  tiledir="${outdir}/tiles";  mkdir -p $tiledir
  BILLING='multifish'
  PYTHON='/groups/multifish/multifish/big_stream/bin/miniconda3/bin/python3'
  SCRIPTS='/groups/multifish/multifish/fleishmang/air_localize'
  CUT_TILES="$PYTHON ${SCRIPTS}/cut_tiles.py"
  AIR_LOCALIZE="$PYTHON ${SCRIPTS}/air_localize.py"
  LIPOFUSCIN_FILTER="$PYTHON ${SCRIPTS}/lipofuscin_filter.py"
  MERGE_POINTS="$PYTHON ${SCRIPTS}/merge_points.py"
}


# the image from which to find spots
image="/groups/multifish/multifish/Yuhan/Stitch/CEA_3_R10/Stitch/n5"
# the folder where you'd like all outputs to be written
outdir="/groups/multifish/multifish/fleishmang/alignments/spots_CEA_3_R10"


# the channels from which to find spots
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
# the channel with DAPI
dapi_channel="c2"
# channels needing DAPI bleedthrough correction
dapi_correction_channels="c3"
# DAPI bleedthrough percentage
dapi_percentage="0.24"

# the air localize parameters file
# the numerical parameters related to air localize are found in this file
# TODO: LET'S ALLOW FOR DIFFERENT PARAMETER FILE FOR EACH SPOTS CHANNEL
params="/groups/multifish/multifish/fleishmang/air_localize/air_localize_default_params.txt"


# DO NOT EDIT BELOW THIS LINE
air_localize='/groups/multifish/multifish/fleishmang/air_localize/air_localize.sh'
bash "$air_localize" "$image" "$channel" "$scale" "$xy_stride" \
     "$xy_overlap" "$z_stride" "$z_overlap" "$params" "$outdir" \
     "$dapi_channel" "$dapi_correction_channels" "$dapi_percentage"


image=${1?}; shift
channels=${1?}; shift
scale=${1?}; shift
xy_stride=${1?}; shift
xy_overlap=${1?}; shift
z_stride=${1?}; shift
z_overlap=${1?}; shift
params=${1?}; shift
outdir=${1?}; shift
dapi_channel=${1?}; shift
dapi_correction_channels=${1?}; shift
dapi_percentage=${1?}; shift

channels=(${channels//,/ })
dapi_correction_channels=(${dapi_correction_channels//,/ })

# TODO: add prefix based on fixed/moving paths to job names to avoid
#       dependency conflict between simultaneous runs

initialize_environment

submit "cut_tiles" '' 1 \
$CUT_TILES $image /${channels[0]}/${scale} $tiledir $xy_stride $xy_overlap $z_stride $z_overlap

while [[ ! -f ${tiledir}/0/coords.txt ]]; do
    sleep 1
done
sleep 5

for channel in ${channels[@]}; do

  if [[ " ${dapi_correction_channels[@]} " =~ " ${channel} " ]]; then
    dapi_correction="/${dapi_channel}/${scale} $dapi_percentage"
  else
    dapi_correction=""
  fi

  for tile in $( ls -d ${tiledir}/*[0-9] ); do
      tile_num=`basename $tile`
      submit "air_localize${tile_num}_${channel}" '' 1 \
      $AIR_LOCALIZE $image /${channel}/${scale} ${tile}/coords.txt $params $tile _${channel}.txt \
                    $dapi_correction
  done

  # TODO: make sure this works
#  if [[ " $LIPOFUSCIN_DETECTION " == 1 ]]; then
    for tile in $( ls -d ${tiledir}/*[0-9] ); do
      tile_num=`basename $tile`
      submit "lipofuscin_filter${tile_num}" "air_localize${tile_num}*" 1 \
      $LIPOFUSCIN_FILTER ${tile}/air_localize_points_c0.txt ${tile}/air_localize_points_c1.txt ${tile} 1.28 0.42 0.999
    done
#  fi
  # TODO: end todo


  submit "merge_points" "air_localize*_${channel}" 1 \
  $MERGE_POINTS $tiledir _${channel}.txt ${outdir}/merged_points_${channel}.txt \
                $xy_overlap $z_overlap $image /${channel}/${scale}
done

