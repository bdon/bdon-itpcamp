import rasterio
import rasterio.mask
import fiona
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds, transform_geom
from shapely.validation import explain_validity
from shapely.geometry import shape

TIFF_URL = "https://naipeuwest.blob.core.windows.net/naip/v002/ny/2022/ny_060cm_2022/40073/m_4007317_sw_18_060_20220719.tif"
TIFF_URL = "mosaic.vrt"

wgs_bounds = (-73.991339,40.678184,-73.986517,40.696261)


with rasterio.open(TIFF_URL) as src:
  # bounds = transform_bounds("EPSG:4326", src.crs, *wgs_bounds, densify_pts=21)

  with fiona.open("prospectpark.geojson", "r") as shap:
    transformed_geom = transform_geom(
      src_crs=shap.crs,
      dst_crs=src.crs,
      geom=shap[0].geometry
    )
    poly = shape(transformed_geom)
    print(explain_validity(poly))
    bounds = rasterio.features.bounds(transformed_geom)
    window = from_bounds(*bounds, transform=src.transform)
    transform = src.window_transform(window)
    out_image, out_transform = rasterio.mask.mask(src, [poly], crop=True)

    data = src.read(window=window)
    with rasterio.open(
          "out.tif", "w",
          driver="GTiff",
          height=data.shape[1],
          width=data.shape[2],
          count=src.count,
          dtype=data.dtype,
          crs=src.crs,
          transform=transform
      ) as dst:
          dst.write(out_image)