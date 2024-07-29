GOOGLE CLOUD SHELL DEPLOYMENT:
  1. Created a artifact repository name osmregistry
  2. ran "docker build -t osm ." to create an image called osm
  3. Tested image with "docker run --rm -p 8080:8080 -e PORT=8080 osm" (-e {key=value})
  4. tagged image to repository with "docker tag osm:latest us-central1-docker.pkg.dev/openseatmonitor/osmregistry/osm:latest"
  5. Pushed tagged image to repository with "docker push us-central1-docker.pkg.dev/openseatmonitor/osmregistry/osm:latest"
  6. Created a service with the image in the osmregistry artifact registry and deployed.

Useful Docker commands: 
  1. Remove all images: docker rmi $(docker images -q)
  2. See all containers: docker ps -a
  3. See all images: docker image ls
