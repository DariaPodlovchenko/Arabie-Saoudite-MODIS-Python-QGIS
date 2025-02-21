# Chargement des données source
uri = ""
modistest = QgsVectorLayer(uri, "Données d'origine", "delimitedtext")

# Vérification de la validité du layer source
if not modistest.isValid():
    print("Le layer original n'est pas valide !")
else:
    print(f"Le layer original est valide. Nombre d'entités : {modistest.featureCount()}")
    
    # Création d'une copie en mémoire
    memory_layer = QgsVectorLayer("Point?crs=epsg:4326", "Editable Copy", "memory")
    dataProvider = memory_layer.dataProvider()

    # Copie des attributs du layer source
    dataProvider.addAttributes(modistest.fields())
    memory_layer.updateFields()

    # Copie des entités
    features = [feat for feat in modistest.getFeatures()]
    dataProvider.addFeatures(features)
    QgsProject.instance().addMapLayer(memory_layer)
    print(f"Copied layer feature count: {memory_layer.featureCount()}")

    # Suppression des entités avec 'confidence' <= 70 ou 'type' != 2
    to_delete = [feature.id() for feature in memory_layer.getFeatures() if feature['confidence'] <= 70 or feature['type'] != 2]
    memory_layer.dataProvider().deleteFeatures(to_delete)
    memory_layer.updateFields()

    # Démarrage de l'édition et ajout de nouveaux champs pour l'agrégation
    memory_layer.startEditing()
    memory_layer.dataProvider().addAttributes([
        QgsField("days_burning", QVariant.Int),
        QgsField("average_frp", QVariant.Double),
        QgsField("average_brightness", QVariant.Double),
        QgsField("average_bright_t31", QVariant.Double)
    ])
    memory_layer.updateFields()

    # Agrégation des données par date d'acquisition
    aggregated_data = {}
    for feature in memory_layer.getFeatures():
        date_key = feature['acq_date']  # Assurez-vous que 'acq_date' est bien une chaîne de caractères
        if date_key not in aggregated_data:
            aggregated_data[date_key] = {
                'feature': feature,
                'total_frp': 0,
                'total_brightness': 0,
                'total_bright_t31': 0,
                'count': 0
            }
        aggregated_data[date_key]['total_frp'] += feature['frp'] or 0
        aggregated_data[date_key]['total_brightness'] += feature['brightness'] or 0
        aggregated_data[date_key]['total_bright_t31'] += feature['bright_t31'] or 0
        aggregated_data[date_key]['count'] += 1
    
    # Suppression des entités existantes et ajout des entités agrégées
    memory_layer.dataProvider().truncate()
    
    new_features = []
    for data in aggregated_data.values():
        new_feature = QgsFeature(memory_layer.fields())
        new_feature.setGeometry(data['feature'].geometry())
        for field in data['feature'].fields():
            new_feature[field.name()] = data['feature'][field.name()]
        new_feature['days_burning'] = data['count']
        new_feature['average_frp'] = data['total_frp'] / data['count'] if data['count'] > 0 else 0
        new_feature['average_brightness'] = data['total_brightness'] / data['count'] if data['count'] > 0 else 0
        new_feature['average_bright_t31'] = data['total_bright_t31'] / data['count'] if data['count'] > 0 else 0
        new_features.append(new_feature)
    
    memory_layer.dataProvider().addFeatures(new_features)
    memory_layer.commitChanges()
    print("Agrégation des données terminée.")
    
    # Suppression des champs inutiles
    fields_to_delete = ['track', 'scan', 'brightness', 'bright_t31', 'frp', 'acq_time', 'version', 'daynight']
    field_indices = [memory_layer.fields().indexFromName(field_name) for field_name in fields_to_delete]
    memory_layer.startEditing()
    memory_layer.dataProvider().deleteAttributes(field_indices)
    memory_layer.commitChanges()
    print("Champs inutilisés supprimés.")
    
    # Création d'un buffer de 60 m autour des points
    buffer_params = {
        'INPUT': memory_layer,
        'DISTANCE': 60,
        'SEGMENTS': 10,
        'OUTPUT': 'memory:'
    }
    buffer_layer = processing.run("native:buffer", buffer_params)['OUTPUT']
    
    # Dissolution des buffers pour fusionner les zones superposées
    dissolved_layer = processing.run("native:dissolve", {
        'INPUT': buffer_layer,
        'OUTPUT': 'memory:'
    })['OUTPUT']
    
    # Indexation spatiale pour sélectionner les points dans les buffers fusionnés
    selected_features = []
    index = QgsSpatialIndex(dissolved_layer.getFeatures())
    for feature in memory_layer.getFeatures():
        if index.intersects(feature.geometry().boundingBox()):
            selected_features.append(feature.id())
    
    # Sélection des entités dans le layer
    memory_layer.selectByIds(selected_features)
    QgsProject.instance().addMapLayer(memory_layer)
    print(f"Sélection de {len(selected_features)} points situés à moins de 60 m les uns des autres.")
