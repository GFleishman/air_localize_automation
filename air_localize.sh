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
  PYTHON='/groups/scicompsoft/home/fleishmang/bin/miniconda3/bin/python3'
  SCRIPTS='/groups/multifish/multifish/fleishmang/air_localize'
  CUT_TILES="$PYTHON ${SCRIPTS}/cut_tiles.py"
  AIR_LOCALIZE="$PYTHON ${SCRIPTS}/air_localize.py"
  MERGE_POINTS="$PYTHON ${SCRIPTS}/merge_points.py"
}


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

  submit "merge_points" "air_localize*_${channel}" 1 \
  $MERGE_POINTS $tiledir _${channel}.txt ${outdir}/merged_points_${channel}.txt \
                $xy_overlap $z_overlap $image /${channel}/${scale}
done

