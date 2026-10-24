# SPDX-License-Identifier: GPL-3.0-or-later
"""Review the three-wall native exchange fixture in the actual Bonsai application.

Run with Blender's --python option, placing this script's arguments after --.
Bonsai must already be installed and enabled in a disposable Blender profile.
This harness clears the current scene. Never run it in an unsaved user project.

See docs/BONSAI_REVIEW.md for exact fixture paths, installation sources, GUI
capture review and the distinction between 41 application checks and 42 checks
including a visible, inspected GUI capture. No software is installed by this file.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import traceback


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    for option, variable, help_text in (
        ("ifc", "BIM3117_REVIEW_IFC", "Native-exported IFC fixture"),
        ("snapshot", "BIM3117_REVIEW_SNAPSHOT", "Matching native snapshot JSON"),
        ("native-report", "BIM3117_REVIEW_NATIVE_REPORT", "Passing native test report with independent expected volumes"),
        ("output", "BIM3117_REVIEW_OUTPUT", "Fresh review output directory"),
    ):
        parser.add_argument("--" + option, default=os.environ.get(variable),
                            help=help_text + " (or " + variable + ")")
    parser.add_argument("--gui-hold-seconds", type=float, default=12.0,
                        help="Seconds to keep GUI open after capture.ready; 0 keeps it open")
    # Blender retains its own arguments in sys.argv. Environment-only use is valid.
    extra = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = parser.parse_args(extra)
    for name in ("ifc", "snapshot", "native_report", "output"):
        value = getattr(args, name)
        if not value:
            parser.error("--" + name.replace("_", "-") + " or its environment variable is required")
        setattr(args, name, Path(value).expanduser().resolve())
    for name in ("ifc", "snapshot", "native_report"):
        if not getattr(args, name).is_file():
            parser.error("Input file does not exist: " + str(getattr(args, name)))
    if not math.isfinite(args.gui_hold_seconds) or args.gui_hold_seconds < 0:
        parser.error("--gui-hold-seconds must be finite and nonnegative")
    args.output.mkdir(parents=True, exist_ok=True)
    for name in ("bonsai-application-report.json", "capture.ready", "Bonsai_Native_IFC_Review.png"):
        if (args.output / name).exists():
            parser.error("Use a fresh output directory; evidence already exists: " + str(args.output / name))
    return args


ARGS = arguments()

# These dependencies belong to the already installed Blender/Bonsai runtime.
import bpy
import bonsai
import bonsai.tool as tool
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.validate
from mathutils import Vector

OUT = ARGS.output
IFC = ARGS.ifc
SNAPSHOT = json.loads(ARGS.snapshot.read_text(encoding="utf-8"))
SOURCE_REPORT = json.loads(ARGS.native_report.read_text(encoding="utf-8"))
report = {'status':'running','blender':bpy.app.version_string,'blender_build_hash':bpy.app.build_hash.decode(),
          'bonsai':bonsai.bbim_semver['version'],'ifcopenshell':ifcopenshell.version,
          'python':sys.version,'platform':platform.platform(),'background':bpy.app.background,
          'review_mode':'background_application' if bpy.app.background else 'gui_application',
          'visual_review':{'status':'not_run' if bpy.app.background else 'capture_pending'},
          'source_snapshot':str(ARGS.snapshot),'source_native_report':str(ARGS.native_report),
          'source_ifc':str(IFC),'source_sha256':hashlib.sha256(IFC.read_bytes()).hexdigest(),
          'content_revision':SNAPSHOT['content_revision'],'checks':[], 'wall_observations':[],
          'door_observations':[], 'scope':'Actual Bonsai import, Blender meshes/rays, IFC metadata and EXPRESS schema. Bonsai uses IfcOpenShell; not evidence of another IFC geometry kernel.'}


def check(name, good):
    if not good: raise AssertionError(name)
    report['checks'].append({'name':name,'status':'passed'})


def near(a,b):
    return abs(float(a)-float(b)) <= max(2e-6, abs(float(b))*2e-6)


def guid(identifier):
    return ifcopenshell.guid.compress(identifier.replace('-',''))


def world_vertices(obj):
    return [obj.matrix_world @ v.co for v in obj.data.vertices]


def mesh_volume(obj):
    vertices=world_vertices(obj); obj.data.calc_loop_triangles()
    origin=tuple(vertices[0])
    points=[tuple(float(v[i])-origin[i] for i in range(3)) for v in vertices]
    def determinant(tri):
        a,b,c=(points[i] for i in tri.vertices)
        return a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+a[2]*(b[0]*c[1]-b[1]*c[0])
    return abs(math.fsum(determinant(t) for t in obj.data.loop_triangles)/6.0)


def wall_point(wall, along, across, elevation):
    start=Vector((*wall['start_m'],wall['base_z_m']))
    ux=(wall['end_m'][0]-wall['start_m'][0])/wall['length_m']
    uy=(wall['end_m'][1]-wall['start_m'][1])/wall['length_m']
    return start+Vector((ux*along-uy*across,uy*along+ux*across,elevation))


def ray(obj, wall, along, elevation):
    start=wall_point(wall,along,-0.2,elevation)
    finish=wall_point(wall,along,wall['thickness_m']+0.2,elevation)
    inv=obj.matrix_world.inverted(); a=inv@start; b=inv@finish
    return obj.ray_cast(a,(b-a).normalized(),distance=(b-a).length)[0]


def bbox_matches(obj,wall,along=0,across=0,z=0,length=None,depth=None,height=None):
    length=wall['length_m'] if length is None else length
    depth=wall['thickness_m'] if depth is None else depth
    height=wall['height_m'] if height is None else height
    expected=[wall_point(wall,along+x,across+y,z+h) for x in (0,length) for y in (0,depth) for h in (0,height)]
    actual=world_vertices(obj)
    return all(near(min(v[a] for v in actual),min(v[a] for v in expected))
               and near(max(v[a] for v in actual),max(v[a] for v in expected)) for a in range(3))


def write_report():
    report['checks_passed']=len(report['checks'])
    (OUT/'bonsai-application-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


def inspect():
    try:
        check('source comes from passing installed-native exchange tests',SOURCE_REPORT['status']=='passed')
        for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
        status=bpy.ops.bim.load_project(filepath=str(IFC),should_start_fresh_session=False,
                                        skip_recent=True,skip_autosave_recovery=True)
        check('public Bonsai Load IFC Project operator finishes',status=={'FINISHED'})
        model=tool.Ifc.get()
        check('active Bonsai file is IFC4 with expected product and storey counts',
              model.schema=='IFC4' and len(model.by_type('IfcWall'))==3 and len(model.by_type('IfcDoor'))==3
              and len(model.by_type('IfcOpeningElement'))==3 and len(model.by_type('IfcWallType'))==1
              and len(model.by_type('IfcBuildingStorey'))==3)
        check('Bonsai scene uses metre scale',near(bpy.context.scene.unit_settings.scale_length,1.0))
        check('no duplicate IfcRoot GlobalIds',len({e.GlobalId for e in model.by_type('IfcRoot')})==len(model.by_type('IfcRoot')))
        walls={w['id']:w for w in SNAPSHOT['walls']}
        for wall in SNAPSHOT['walls']:
            entity=model.by_guid(guid(wall['id']));obj=tool.Ifc.get_object(entity);label=wall['label']
            check(label+': Bonsai maps IFC wall to a native Blender mesh',obj is not None and obj.type=='MESH' and tool.Ifc.get_entity(obj)==entity)
            props=ifcopenshell.util.element.get_psets(entity)
            typ=ifcopenshell.util.element.get_type(entity)
            container=ifcopenshell.util.element.get_container(entity)
            check(label+': UUID type base level and content revision retained',
                  props['BIM3117_Source']['SourceUUID']==wall['id']
                  and props['BIM3117_Source']['ContentRevision']==SNAPSHOT['content_revision']
                  and typ.GlobalId==guid(wall['type_id']) and container.GlobalId==guid(wall['base_level_id']))
            volume=mesh_volume(obj);expected=SOURCE_REPORT['expected_net_volumes_m3'][wall['id']]
            report.setdefault('volume_diagnostics',[]).append({'name':label,'mesh_volume_m3':volume,'expected':expected,'absolute_error':abs(volume-expected)})
            check(label+': independent Blender triangle volume matches native fixture',near(volume,expected))
            check(label+': world mesh bounds match authored axis and signed level offsets',bbox_matches(obj,wall))
            check(label+': imported quantity property matches actual Blender mesh volume',near(props['Qto_WallBaseQuantities']['NetVolume'],volume))
            report['wall_observations'].append({'source_uuid':wall['id'],'ifc_guid':entity.GlobalId,'name':label,
                                               'blender_object':obj.name,'mesh_volume_m3':volume,'expected_net_volume_m3':expected,
                                               'vertices':len(obj.data.vertices),'polygons':len(obj.data.polygons)})
        for door in SNAPSHOT['doors']:
            wall=walls[door['host_id']];host=model.by_guid(guid(wall['id']));host_obj=tool.Ifc.get_object(host)
            entity=model.by_guid(guid(door['id']));obj=tool.Ifc.get_object(entity);label=door['label']
            check(label+': Bonsai maps IFC door frame to Blender mesh',obj is not None and obj.type=='MESH' and tool.Ifc.get_entity(obj)==entity)
            opening=entity.FillsVoids[0].RelatingOpeningElement
            props=ifcopenshell.util.element.get_psets(entity)['BIM3117_Source']
            check(label+': void fill host and source identity retained',opening.VoidsElements[0].RelatingBuildingElement==host
                  and props['SourceUUID']==door['id'] and props['HostWallUUID']==wall['id']
                  and props['ContentRevision']==SNAPSHOT['content_revision'])
            volume=mesh_volume(obj)
            check(label+': frame mesh volume and world placement match native frame',
                  near(volume,door['frame_volume_m3']) and bbox_matches(obj,wall,along=door['offset_m'],z=door['sill_m'],
                       length=door['width_m'],height=door['height_m']))
            centre=door['offset_m']+door['width_m']/2
            z=door['sill_m']+door['height_m']/2
            check(label+': ray crosses actual wall opening without hitting wall mesh',not ray(host_obj,wall,centre,z))
            check(label+': adjacent jamb and head remain wall material',ray(host_obj,wall,max(0.05,door['offset_m']/2),z)
                  and ray(host_obj,wall,centre,door['sill_m']+door['height_m']+0.05))
            strip=min(.05,door['width_m']/4,door['height_m']/4)
            check(label+': generic frame has open centre and solid jamb',not ray(obj,wall,centre,z)
                  and ray(obj,wall,door['offset_m']+strip/2,z))
            report['door_observations'].append({'source_uuid':door['id'],'ifc_guid':entity.GlobalId,'name':label,
                                               'blender_object':obj.name,'host_uuid':wall['id'],'mesh_frame_volume_m3':volume})
        check('Bonsai mesh objects contain exactly the six declared authored products',
              len([o for o in bpy.data.objects if o.type=='MESH' and tool.Ifc.get_entity(o) is not None])==6)
        logger=ifcopenshell.validate.json_logger()
        ifcopenshell.validate.validate(model,logger,express_rules=True)
        report['express_validation']={'statements':logger.statements,'count':len(logger.statements)}
        check('independent Bonsai runtime full schema and EXPRESS validation has no findings',not logger.statements)
        check('opening IFC in Bonsai does not rewrite the source bytes',hashlib.sha256(IFC.read_bytes()).hexdigest()==report['source_sha256'])
        report['status']='passed'
        if not bpy.app.background:
            bpy.ops.object.select_all(action='DESELECT')
            target=tool.Ifc.get_object(model.by_guid(guid(SOURCE_REPORT['element_ids'][SOURCE_REPORT['element_names']['wall']])))
            target.select_set(True);bpy.context.view_layer.objects.active=target
            for area in bpy.context.screen.areas:
                if area.type=='VIEW_3D':
                    space=area.spaces.active
                    space.shading.type='SOLID';space.shading.color_type='MATERIAL'
                    space.overlay.show_floor=False;space.overlay.show_axis_x=False;space.overlay.show_axis_y=False
                    space.region_3d.view_perspective='ORTHO'
                    space.region_3d.view_location=Vector((2.7,4.7,.15))
                    space.region_3d.view_distance=17.0
                    space.region_3d.view_rotation=Vector((13,-21,16)).to_track_quat('Z','Y')
                    space.show_region_ui=False
                elif area.type=='PROPERTIES':
                    area.spaces.active.context='SCENE'
                area.tag_redraw()
            bpy.app.timers.register(finish_gui,first_interval=2.0)
        else:write_report()
    except BaseException as error:
        report.update(status='failed',error=str(error),traceback=traceback.format_exc());write_report()
        if not bpy.app.background:bpy.app.timers.register(quit_app,first_interval=0.2)
        else:raise
    return None


def quit_app():
    bpy.ops.wm.quit_blender()
    return None


def finish_gui():
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP',iterations=3)
        report['status']='geometry_passed_capture_pending'
        report['screenshot']=str(OUT/'Bonsai_Native_IFC_Review.png')
        write_report()
        (OUT/'capture.ready').write_text('ready',encoding='utf-8')
    except BaseException as error:
        report.update(status='failed',error=str(error),traceback=traceback.format_exc());write_report()
    if ARGS.gui_hold_seconds:
        bpy.app.timers.register(quit_app,first_interval=ARGS.gui_hold_seconds)
    return None


if bpy.app.background:inspect()
else:bpy.app.timers.register(inspect,first_interval=1.0)
