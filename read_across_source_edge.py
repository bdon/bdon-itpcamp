import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds

# What if I have two adjacent source TIFFs, and my area of interest crosses the edge?
# these two TIFFs below are adjacent:
# TIFF_URL = "https://naipeuwest.blob.core.windows.net/naip/v002/ny/2022/ny_060cm_2022/40073/m_4007317_nw_18_060_20220719.tif"
TIFF_URL = "https://naipeuwest.blob.core.windows.net/naip/v002/ny/2022/ny_060cm_2022/40073/m_4007317_sw_18_060_20220719.tif"

# the solution is to build a VRT:
# gdalbuildvrt mosaic.vrt /vsicurl/URL1 /vsicurl/URL2
# TIFF_URL = "mosaic.vrt"

wgs_bounds = (-73.991339,40.678184,-73.986517,40.696261)

with rasterio.open(TIFF_URL) as src:
  bounds = transform_bounds("EPSG:4326", src.crs, *wgs_bounds, densify_pts=21)
  window = from_bounds(*bounds, transform=src.transform)
  transform = src.window_transform(window)
  data = src.read(window=window)
  with rasterio.open(
        "read_across_source_edge.tif", "w",
        driver="GTiff",
        height=data.shape[1],
        width=data.shape[2],
        count=src.count,
        dtype=data.dtype,
        crs=src.crs,
        transform=transform
    ) as dst:
        dst.write(data)