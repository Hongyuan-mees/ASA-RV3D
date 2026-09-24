# Read-only OpenROAD helper for area-weight balance of an RV3D assignment CSV.
#
# Usage inside ORFS docker_shell/OpenROAD:
#   set env(ODB_FILE) ...
#   set env(ASSIGNMENT_FILE) ...
#   set env(OUTPUT_CSV) ...
#   openroad extract_openroad_assignment_area_balance.tcl

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

proc add_variant {variant canonical area_var status_var} {
  upvar $area_var area_by_variant
  upvar $status_var status_by_variant
  if {$variant eq ""} {
    return
  }
  if {$variant eq $canonical} {
    return
  }
  if {[info exists area_by_variant($variant)]} {
    set status_by_variant($variant) "ambiguous"
  } else {
    set area_by_variant($variant) $area_by_variant($canonical)
    set status_by_variant($variant) "unique"
  }
}

set odb_file [required_env ODB_FILE]
set assignment_file [required_env ASSIGNMENT_FILE]
set output_csv [required_env OUTPUT_CSV]
set design ""
if {[info exists ::env(DESIGN)]} {
  set design $::env(DESIGN)
}
set case_name ""
if {[info exists ::env(CASE)]} {
  set case_name $::env(CASE)
}

read_db $odb_file
set block [ord::get_db_block]

array set area_by_variant {}
array set status_by_variant {}

foreach inst [$block getInsts] {
  set name [normalize_name [$inst getName]]
  set area [[$inst getMaster] getArea]
  set area_by_variant($name) $area
  set status_by_variant($name) "unique"
}

foreach inst [$block getInsts] {
  set name [normalize_name [$inst getName]]
  set slash_to_dot [string map {"/" "."} $name]
  set dot_to_slash [string map {"." "/"} $name]
  set no_escape [string map {"\\" ""} $name]
  add_variant $slash_to_dot $name area_by_variant status_by_variant
  add_variant $dot_to_slash $name area_by_variant status_by_variant
  add_variant $no_escape $name area_by_variant status_by_variant
}

set fp [open $assignment_file r]
set header [gets $fp]
set cols [split $header ","]
set instance_idx [lsearch -exact $cols "instance"]
set tier_idx [lsearch -exact $cols "tier"]
if {$instance_idx < 0 || $tier_idx < 0} {
  puts stderr "assignment CSV must contain instance and tier columns"
  exit 2
}

set part_area(tier0) 0
set part_area(tier1) 0
set count(tier0) 0
set count(tier1) 0
set matched 0
set unmatched 0
set ambiguous 0

while {[gets $fp line] >= 0} {
  if {[string trim $line] eq ""} {
    continue
  }
  set fields [split $line ","]
  set inst [normalize_name [lindex $fields $instance_idx]]
  set tier [lindex $fields $tier_idx]
  if {$tier ne "tier0" && $tier ne "tier1"} {
    continue
  }
  incr count($tier)

  set lookup ""
  foreach candidate [list $inst [string map {"/" "."} $inst] [string map {"." "/"} $inst] [string map {"\\" ""} $inst]] {
    if {[info exists area_by_variant($candidate)] && $status_by_variant($candidate) eq "unique"} {
      set lookup $candidate
      break
    }
  }

  if {$lookup ne ""} {
    set part_area($tier) [expr {$part_area($tier) + $area_by_variant($lookup)}]
    incr matched
  } else {
    set found_ambiguous 0
    foreach candidate [list $inst [string map {"/" "."} $inst] [string map {"." "/"} $inst] [string map {"\\" ""} $inst]] {
      if {[info exists area_by_variant($candidate)]} {
        set found_ambiguous 1
        break
      }
    }
    if {$found_ambiguous} {
      incr ambiguous
    } else {
      incr unmatched
    }
  }
}
close $fp

set total_area [expr {$part_area(tier0) + $part_area(tier1)}]
set lo [expr {$part_area(tier0) < $part_area(tier1) ? $part_area(tier0) : $part_area(tier1)}]
set hi [expr {$part_area(tier0) > $part_area(tier1) ? $part_area(tier0) : $part_area(tier1)}]
set area_balance [expr {$hi > 0 ? double($lo) / double($hi) : 0.0}]
set tier0_fraction [expr {$total_area > 0 ? double($part_area(tier0)) / double($total_area) : 0.0}]
set tier1_fraction [expr {$total_area > 0 ? double($part_area(tier1)) / double($total_area) : 0.0}]
set pass [expr {$tier0_fraction >= 0.48 && $tier0_fraction <= 0.52 ? "true" : "false"}]

set out [open $output_csv w]
puts $out "design,case,assignment_file,tier0_instances,tier1_instances,matched_instances,ambiguous_instances,unmatched_instances,tier0_area_weight,tier1_area_weight,area_weight_balance,tier0_area_fraction,tier1_area_fraction,balance_constraint_2_pass"
puts $out [format "%s,%s,%s,%d,%d,%d,%d,%d,%d,%d,%.6f,%.6f,%.6f,%s" \
  $design $case_name $assignment_file $count(tier0) $count(tier1) $matched $ambiguous $unmatched \
  $part_area(tier0) $part_area(tier1) $area_balance $tier0_fraction $tier1_fraction $pass]
close $out

puts $output_csv
puts [format "area_weight_balance = %.6f" $area_balance]
puts [format "tier0_area_fraction = %.6f" $tier0_fraction]
puts [format "tier1_area_fraction = %.6f" $tier1_fraction]
puts "balance_constraint_2_pass = $pass"
exit
