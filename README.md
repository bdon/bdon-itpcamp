Example of gdalwarp CLI usage to extract a bounding box from a remote GeoTIFF:

```
gdalwarp -te -73.991339 40.6883 -73.97804 40.696261 -te_srs EPSG:4326 /vsicurl/https://naipeuwest.blob.core.windows.net/naip/v002/ny/2022/ny_060cm_2022/40073/m_4007317_nw_18_060_20220719.tif output.tif
```
