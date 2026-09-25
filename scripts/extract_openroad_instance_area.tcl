# Export per-instance OpenROAD master area variants for RV3D guarded refinement.
#
# Usage inside ORFS docker_shell/OpenROAD:
#   DESIGN=picorv32 ODB_FILE=/work/results/.../6_final.odb \
#   OUTPUT_CSV=/work/.../instance_area.csv \
#   openroad scripts/extract_openroad_instance_area.tcl

proc required_env {name} {
  if {![info exists ::env($name)] || $::env($name) eq ""} {
    puts stderr "missing environment variable: $name"
    exit 2
  }
  return $::env($name)
}

proc normalize_name {name} {
  set out [string trim $name]
  if {[string index $out 0] eq "\\"} {
    set out [string range $out 1 end]
  }
  return $out
}

set odb_file [required_env ODB_FILE]
set output_csv [required_env OUTPUT_CSV]
set design ""
if {[info exists ::env(DESIGN)]} {
  set design $::env(DESIGN)
}

read_db $odb_file
set block [ord::get_db_block]

array set area_by_variant {}
array set canonical_by_variant {}
array set status_by_variant {}

proc add_variant {variant canonical area_var canonical_var status_var} {
  upvar $area_var area_by_variant
  upvar $canonical_var canonical_by_variant
  upvar $status_var status_by_variant
  if {$variant eq ""} {
    return
  }
  if {[info exists area_by_variant($variant)] && $canonical_by_variant($variant) ne $canonical} {
    set status_by_variant($variant) "ambiguous"
  } else {
    set area_by_variant($variant) $area_by_variant($canonical)
    set canonical_by_variant($variant) $canonical
    set status_by_variant($variant) "unique"
  }
}

foreach inst [$block getInsts] {
  set name [normalize_name [$inst getName]]
  set area [[$inst getMaster] getArea]
  set area_by_variant($name) $area
  set canonical_by_variant($name) $name
  set status_by_variant($name) "unique"
}

foreach inst [$block getInsts] {
  set name [normalize_name [$inst getName]]
  set slash_to_dot [string map {"/" "."} $name]
  set dot_to_slash [string map {"." "/"} $name]
  set no_escape [string map {"\\" ""} $name]
  add_variant $slash_to_dot $name area_by_variant canonical_by_variant status_by_variant
  add_variant $dot_to_slash $name area_by_variant canonical_by_variant status_by_variant
  add_variant $no_escape $name area_by_variant canonical_by_variant status_by_variant
}

set out [open $output_csv w]
puts $out "design,variant,canonical_instance,area,status"
foreach variant [array names area_by_variant] {
  puts $out [format "%s,%s,%s,%d,%s" \
    $design $variant $canonical_by_variant($variant) $area_by_variant($variant) $status_by_variant($variant)]
}
close $out

puts $output_csv
exit
