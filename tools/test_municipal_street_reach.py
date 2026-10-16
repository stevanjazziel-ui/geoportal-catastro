import unittest

import geopandas as gpd
from shapely.geometry import LineString

from audit_municipal_street_reach import road_catalog, trace_arm, source_routes, uncovered_route


def frame(rows):
    return gpd.GeoDataFrame([{'name':n,'highway':'primary','bridge':'no','tunnel':'no','geometry':LineString(xy)} for n,xy in rows],crs=32717)


class StreetReachTests(unittest.TestCase):
    def test_range_is_network_distance(self):
        street=road_catalog(frame([('Eje',[(0,0),(150,0),(300,0)])]))['eje']
        line,reason=trace_arm(street,(0,0),(150,0),straight=True)
        self.assertAlmostEqual(line.length,200);self.assertEqual(list(line.coords)[-1],(200,0))

    def test_no_turn_onto_differently_named_street(self):
        streets=road_catalog(frame([('A',[(0,0),(100,0)]),('B',[(100,0),(100,100)])]))
        self.assertNotIn((100,100),source_routes(streets['a'],(0,0))[0])

    def test_strict_axis_stops_before_curve(self):
        street=road_catalog(frame([('Eje',[(0,0),(100,0),(100,100)])]))['eje']
        self.assertEqual(trace_arm(street,(0,0),(100,0),straight=True)[0].length,100)
        self.assertEqual(trace_arm(street,(0,0),(100,0))[0].length,200)

    def test_geometric_crossing_not_noded(self):
        street=road_catalog(frame([('Eje',[(-10,0),(10,0)]),('Eje',[(0,-10),(0,10)])]))['eje']
        self.assertNotIn((0,10),source_routes(street,(-10,0))[0])

    def test_branch_ambiguity_stops_traversal(self):
        street=road_catalog(frame([('Eje',[(0,0),(100,0),(200,0)]),('Eje',[(100,0),(100,100)])]))['eje']
        self.assertEqual(trace_arm(street,(0,0),(100,0))[1],'BIFURCACION_MISMO_NOMBRE')
        self.assertNotIn((200,0),source_routes(street,(0,0))[0])

    def test_bridge_excluded(self):
        roads=frame([('Eje',[(0,0),(100,0)])]);roads.loc[0,'bridge']='yes'
        self.assertFalse(road_catalog(roads))

    def test_interpolated_edge_uses_numerical_overlay_tolerance(self):
        route=LineString([(761000.123456,9813000.234567),(761333.345678,9813111.456789)])
        edge=LineString([route.coords[0],route.interpolate(200).coords[0]])
        self.assertAlmostEqual(uncovered_route(route,edge).length,route.length-200,places=4)


if __name__=='__main__':
    unittest.main()
