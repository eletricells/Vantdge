2025-12-05T09:22:53.735266941Z [inf]  
2025-12-05T09:22:54.332012330Z [inf]  [35m[Region: us-west1][0m
2025-12-05T09:22:54.333695060Z [inf]  [35m==============
2025-12-05T09:22:54.333722860Z [inf]  Using Nixpacks
2025-12-05T09:22:54.333728528Z [inf]  ==============
2025-12-05T09:22:54.333732698Z [inf]  [0m
2025-12-05T09:22:54.333853863Z [inf]  context: vp82-5jvt
2025-12-05T09:22:54.541593842Z [inf]  ╔══════════════════════════════ Nixpacks v1.38.0 ══════════════════════════════╗
2025-12-05T09:22:54.541640674Z [inf]  ║ setup      │ python311, gcc, ghostscript, poppler_utils                      ║
2025-12-05T09:22:54.541648535Z [inf]  ║──────────────────────────────────────────────────────────────────────────────║
2025-12-05T09:22:54.541653357Z [inf]  ║ install    │ pip install --upgrade pip                                       ║
2025-12-05T09:22:54.541660137Z [inf]  ║            │ pip install -r requirements.txt                                 ║
2025-12-05T09:22:54.541665573Z [inf]  ║──────────────────────────────────────────────────────────────────────────────║
2025-12-05T09:22:54.541670320Z [inf]  ║ start      │ streamlit run frontend/Home.py --server.port ${PORT:-8501}      ║
2025-12-05T09:22:54.541674885Z [inf]  ║            │ --server.address 0.0.0.0 --server.headless true                 ║
2025-12-05T09:22:54.541679700Z [inf]  ╚══════════════════════════════════════════════════════════════════════════════╝
2025-12-05T09:22:54.850235610Z [inf]  [internal] load build definition from Dockerfile
2025-12-05T09:22:54.850284901Z [inf]  [internal] load build definition from Dockerfile
2025-12-05T09:22:54.850529236Z [inf]  [internal] load build definition from Dockerfile
2025-12-05T09:22:54.862786110Z [inf]  [internal] load build definition from Dockerfile
2025-12-05T09:22:54.865881886Z [inf]  [internal] load metadata for ghcr.io/railwayapp/nixpacks:ubuntu-1745885067
2025-12-05T09:22:55.112743227Z [inf]  [internal] load metadata for ghcr.io/railwayapp/nixpacks:ubuntu-1745885067
2025-12-05T09:22:55.113040731Z [inf]  [internal] load .dockerignore
2025-12-05T09:22:55.113071683Z [inf]  [internal] load .dockerignore
2025-12-05T09:22:55.113097190Z [inf]  [internal] load .dockerignore
2025-12-05T09:22:55.124764474Z [inf]  [internal] load .dockerignore
2025-12-05T09:22:55.130882032Z [inf]  [stage-0 9/9] COPY . /app
2025-12-05T09:22:55.130897437Z [inf]  [stage-0 8/9] RUN printf '\nPATH=/opt/venv/bin:$PATH' >> /root/.profile
2025-12-05T09:22:55.130910799Z [inf]  [stage-0 7/9] RUN --mount=type=cache,id=s/2f451e60-6351-4513-93ca-e1c0f23ab1f0-/root/cache/pip,target=/root/.cache/pip pip install -r requirements.txt
2025-12-05T09:22:55.130919504Z [inf]  [stage-0 6/9] RUN --mount=type=cache,id=s/2f451e60-6351-4513-93ca-e1c0f23ab1f0-/root/cache/pip,target=/root/.cache/pip pip install --upgrade pip
2025-12-05T09:22:55.130927999Z [inf]  [stage-0 5/9] COPY . /app/.
2025-12-05T09:22:55.130939286Z [inf]  [stage-0 4/9] RUN nix-env -if .nixpacks/nixpkgs-bc8f8d1be58e8c8383e683a06e1e1e57893fff87.nix && nix-collect-garbage -d
2025-12-05T09:22:55.130948180Z [inf]  [stage-0 3/9] COPY .nixpacks/nixpkgs-bc8f8d1be58e8c8383e683a06e1e1e57893fff87.nix .nixpacks/nixpkgs-bc8f8d1be58e8c8383e683a06e1e1e57893fff87.nix
2025-12-05T09:22:55.130957112Z [inf]  [internal] load build context
2025-12-05T09:22:55.130968339Z [inf]  [stage-0 2/9] WORKDIR /app/
2025-12-05T09:22:55.130984078Z [inf]  [stage-0 1/9] FROM ghcr.io/railwayapp/nixpacks:ubuntu-1745885067@sha256:d45c89d80e13d7ad0fd555b5130f22a866d9dd10e861f589932303ef2314c7de
2025-12-05T09:22:55.130998292Z [inf]  [stage-0 1/9] FROM ghcr.io/railwayapp/nixpacks:ubuntu-1745885067@sha256:d45c89d80e13d7ad0fd555b5130f22a866d9dd10e861f589932303ef2314c7de
2025-12-05T09:22:55.131159251Z [inf]  [internal] load build context
2025-12-05T09:22:55.131412614Z [inf]  [internal] load build context
2025-12-05T09:22:55.139359789Z [inf]  [stage-0 1/9] FROM ghcr.io/railwayapp/nixpacks:ubuntu-1745885067@sha256:d45c89d80e13d7ad0fd555b5130f22a866d9dd10e861f589932303ef2314c7de
2025-12-05T09:22:55.274670827Z [inf]  [internal] load build context
2025-12-05T09:22:55.277630599Z [inf]  [stage-0 2/9] WORKDIR /app/
2025-12-05T09:22:55.277692760Z [inf]  [stage-0 3/9] COPY .nixpacks/nixpkgs-bc8f8d1be58e8c8383e683a06e1e1e57893fff87.nix .nixpacks/nixpkgs-bc8f8d1be58e8c8383e683a06e1e1e57893fff87.nix
2025-12-05T09:22:55.295688157Z [inf]  [stage-0 3/9] COPY .nixpacks/nixpkgs-bc8f8d1be58e8c8383e683a06e1e1e57893fff87.nix .nixpacks/nixpkgs-bc8f8d1be58e8c8383e683a06e1e1e57893fff87.nix
2025-12-05T09:22:55.298473510Z [inf]  [stage-0 4/9] RUN nix-env -if .nixpacks/nixpkgs-bc8f8d1be58e8c8383e683a06e1e1e57893fff87.nix && nix-collect-garbage -d
2025-12-05T09:22:55.511472527Z [inf]  unpacking 'https://github.com/NixOS/nixpkgs/archive/bc8f8d1be58e8c8383e683a06e1e1e57893fff87.tar.gz' into the Git cache...

2025-12-05T09:23:32.106487334Z [inf]  installing 'bc8f8d1be58e8c8383e683a06e1e1e57893fff87-env'

2025-12-05T09:23:34.098749285Z [inf]  these 3 derivations will be built:
  /nix/store/w9wjpgsiwxjv9p6166ax2mns747lmv2c-libraries.drv
  /nix/store/g3lchy17nx4gv4bw71jnpiinxs47bg4s-bc8f8d1be58e8c8383e683a06e1e1e57893fff87-env.drv
  /nix/store/h4ssnapghpmf0zaipfasy6z1bsc2j73x-bc8f8d1be58e8c8383e683a06e1e1e57893fff87-env.drv

2025-12-05T09:23:34.098774482Z [inf]  these 139 paths will be fetched (174.39 MiB download, 709.53 MiB unpacked):

2025-12-05T09:23:34.098876904Z [inf]    /nix/store/0dglgnjm2s5qg4ar6m33lpclqig0kg2x-acl-2.3.2
  /nix/store/j2v823114cc2dqfvprlcx9h7i941kknh-attr-2.5.2
  /nix/store/515aba55q2b288xzamgb2xl1y1x4sk13-audit-4.0
  /nix/store/gc4s51ksbm026n2wcb68i1myk333zwdr-avahi-0.8
  /nix/store/mm0pa3z7kk6jh1i9rkxqxjqmd8h1qpxf-bash-5.2p37
  /nix/store/j5n790vpyjnqc9kz31s9k8limg5jbk37-bash-interactive-5.2p37
  /nix/store/pbixrqd120nnw8a0ygfpm3mnwlr1mbj7-binutils-2.43.1
  /nix/store/ywxfq90ijq9kys4g5wzyrg2f4in0iphd-binutils-2.43.1-lib
  /nix/store/l13l2ipc1xn5npjrw511y0yfh4ghinmf-binutils-wrapper-2.43.1
  /nix/store/q4hiqvr973mpf0g4jpqg8xa5r8p8qa18-brotli-1.1.0-lib
  /nix/store/nzi7rdydpky7lxv6mlvgcdpvdasaxcmq-builder.pl
  /nix/store/6amvjdayglsifq4lb2lrj4q5gwf4dicd-bzip2-1.0.8
  /nix/store/0kxxaix9l5dbih90491mv96zajsac57q-bzip2-1.0.8-bin
  /nix/store/ydh8c59mzliwy6pvjbrmzvgirryn96qh-cairo-1.18.2
  /nix/store/sf6y4arqcm100rnnl3dhpg732i774zp6-coreutils-9.5
  /nix/store/3mfk8bbdm218328q4m8ldfdkir4s6969-cups-2.4.11
  /nix/store/ivbsicn5yzqqhvr64x9d88l8dz4m6n76-cups-2.4.11-lib
  /nix/store/vic96jkyhfvq58bwch08618zg72gdgkz-curl-8.10.1
  /nix/store/lbx3j21p2dsr1rc5j2s8zaprkkwlrq5x-db-4.8.30
  /nix/store/mpwzncl2rnvybrlcn1m6f3ixs08kj2rm-dbus-1.14.10-lib
  /nix/store/6rvfplkwwbipv2ky3zcab0w9fvib9cgc-dejavu-fonts-minimal-2.37
  /nix/store/alq4bqllykgwrif112yqgrn9g001kn7b-diffutils-3.10
  /nix/store/bcl5fxfdw4h562in7kgyz3m5xjx0wcc3-dns-root-data-2024-06-20
  /nix/store/b1rvxspjrw0f3y5iz4pcygams0n9yas4-ed-1.20.2
  /nix/store/zx2bmicmgjh0inkgffd7agxz47j4xxql-expand-response-params

2025-12-05T09:23:34.09888748Z [inf]    /nix/store/cnmw0v80xbp4ldc79an5kb2p8a3ia6k5-expat-2.6.3
  /nix/store/vkv9a83hknlnr7p2z8mwl16j5pb502gp-file-5.45
  /nix/store/psjqqbj19n3fqssn38hgz4cv7b7a9alp-findutils-4.10.0
  /nix/store/8afqxzzfwf3kfr117ficqzla55az8fcm-fontconfig-2.15.0
  /nix/store/znz0rdiqy03vx45mhayrxfhq2winhd9m-fontconfig-2.15.0-lib
  /nix/store/pg8kdhlacrhv0nsfpx91x9f56gaxqqvv-freetype-2.13.3
  /nix/store/1cd3p3kjh9c209s7832z8i3b8qcqggca-gawk-5.3.1
  /nix/store/v7dbfh5n7az2lcap0z1cv4jq0bikya8p-gcc-13.3.0

2025-12-05T09:23:34.098975216Z [inf]    /nix/store/s94fwp43xhzkvw8l8nqslskib99yifzi-gcc-13.3.0-lib
  /nix/store/c91k93z9yr1cpia2pf5dr226imglrkg5-gcc-13.3.0-libgcc
  /nix/store/zls8qr49k7bkdfb9ncqz9w38q5m8zkld-gcc-13.3.0-man
  /nix/store/hgw57m0jh2w10jsv8x86ng267pm5sla8-gcc-wrapper-13.3.0
  /nix/store/bhd4nlz0993jcsmp7b4fpgjyc9knh1yx-gcc-wrapper-13.3.0-man
  /nix/store/h9bcdwky1hznar341kl52g7hidcjxfdc-gdbm-1.24-lib
  /nix/store/hql3c9ylksa8hzavl1xr675ry4fqj1hb-getent-glibc-2.40-36
  /nix/store/00k65b5bmwji0q799jq6nc4drhww1ij2-ghostscript-with-X-10.04.0
  /nix/store/6q2302j98mzvnbr9aizw3i6ana5aajqv-ghostscript-with-X-10.04.0-fonts
  /nix/store/63kqkhyn0mwk5iam1vc96qmy1hhq5q7g-ghostscript-with-X-10.04.0-man
  /nix/store/zxglqixhhlfppn5z4sszil1cj27ip2jx-giflib-5.2.2
  /nix/store/ipqijizc7rqsxifxc6ky16hr5l0hpls2-glib-2.82.1
  /nix/store/3bvxjkkmwlymr0fssczhgi39c3aj1l7i-glibc-2.40-36
  /nix/store/5571d6dklkwfcp1812dj4lxb0gl3w1yw-glibc-2.40-36-bin
  /nix/store/932dj5qwfzck90mnvqpd1f9hjqznaqdj-glibc-2.40-36-dev
  /nix/store/az5vszpdy3i53lksl8rbjai7bc88r5zs-glibc-2.40-36-getent
  /nix/store/fbir2hb0b8b9n9by2qkmr4sjscds5017-gmp-6.3.0
  /nix/store/avd3viplh1hsz0xcvi86wcfqxycrv2wd-gmp-with-cxx-6.3.0
  /nix/store/i2bs001zwvii9qbhk6mm291gqybpij87-gmp-with-cxx-6.3.0
  /nix/store/vcwb5qr1yjn3pwbm9gnmvqmn1gwg9a1y-gnu-config-2024-01-01
  /nix/store/nysgss3ggh3dv7mz08n28h29lazxhyc1-gnugrep-3.11
  /nix/store/iyrpqn6ana7j804dzis338n74kzznmj0-gnumake-4.4.1

2025-12-05T09:23:34.098985936Z [inf]    /nix/store/13wxcn0j2wk911ahfkbvdq241rkprsv8-gnused-4.9
  /nix/store/cqyjb712c5q3axw9qjij05dnji2a7z48-gnutar-1.35
  /nix/store/d4n6v15i5sl6yxr4qkcw0dq3nmb85kb8-gnutls-3.8.6
  /nix/store/qfc6wq1wpxvkkjqa6xr5685ip97qc3sr-gzip-1.13
  /nix/store/nxy5dn4640120b49836q3xh6nzvfwswf-ijs-10.04.0
  /nix/store/1v4kdwh68m221n160qxy1dgw64mg5z30-isl-0.20
  /nix/store/7g0kqn1d1jh67hn1bazamxg0kz1gl8sm-jbig2dec-0.20
  /nix/store/n3c0dpm00k7s7wgq35b6w025g2ixg20r-kbd-2.6.4
  /nix/store/q8h3pgwxqcgr5v5m7a53hy64vn4n9s79-kexec-tools-2.0.29
  /nix/store/qzsiapz58wbfn8k3j7cbby6n1v0scd53-keyutils-1.6.3-lib

2025-12-05T09:23:34.098995065Z [inf]    /nix/store/grmqrfmxxkbxk83vkki5s45dch8z58yf-kmod-31
  /nix/store/pkh3j1nsqlq0gqiqbsdw7s1pjg5i9nb4-kmod-31-lib
  /nix/store/nns4azjdb9ly7c4mjd5bhnj9zbr03fr0-krb5-1.21.3-lib

2025-12-05T09:23:34.09899896Z [inf]    /nix/store/8ai72nk8pvdsn4lbw67n0i1rp65ygpdg-lcms2-2.16
  /nix/store/qyax1vn63hxggnj0fzbr2xyri3rikpgh-lerc-4.0.0
  /nix/store/ww7q95lqp62aa4d4ss2g5mblzagqz4c4-libICE-1.1.1

2025-12-05T09:23:34.099025706Z [inf]    /nix/store/r97qr0giscd7576l0177inhrvj9xw00v-libSM-1.2.4
  /nix/store/8nbr24sqvsvsfrb5d2nci1ylppjnrwr2-libX11-1.8.10
  /nix/store/7ch80860hzh4hk2xlni7aikdv4nx5jjl-libXau-1.0.11
  /nix/store/6rpcqg6k1kdjnvbcnfx7nm4p185bp2dr-libXdmcp-1.1.5
  /nix/store/d7fhpn9bhzcn521clna2wffmq3ww21zs-libXext-1.3.6
  /nix/store/rindram6f9gwanvazd2x543gis4yzqks-libXrender-0.9.11
  /nix/store/f5rndjaqlq8v9fs70x8cz7r66z6nj4hs-libXt-1.3.0
  /nix/store/ycavj0wxnz72h0n7csvplbgfcrq25x5f-libcap-2.70-lib

2025-12-05T09:23:34.099030245Z [inf]    /nix/store/r5s8n5fr61562pgrl5in513v9ww336wf-libdaemon-0.14
  /nix/store/m8wfhgwjzi8kw3kcbwr241kp1k1nn8jb-libdeflate-1.22

2025-12-05T09:23:34.099033102Z [inf]    /nix/store/qq5ksis6nqh587vl72xj484l8fivaajw-libevent-2.1.12
  /nix/store/0qiyy7llb8ldillvlvjz1pyawhs5cvpk-libffi-3.4.6

2025-12-05T09:23:34.099036319Z [inf]    /nix/store/3wjcy2waiy7cr1v0kvi73aj6i90d878d-libidn2-2.3.7

2025-12-05T09:23:34.099051183Z [inf]    /nix/store/d73s0l3nbc9bpl4c8cg9j12bak5n2d5f-libjpeg-turbo-3.0.3
  /nix/store/wjvrhcaf0qjh4j463sz0fdday7qx8ga8-libmpc-1.3.1
  /nix/store/7vw61y339hgb9s457ga3il7crhh3zh53-libpaper-1.1.29
  /nix/store/d497qsaaabx4nqchkrrzvaimad6mp22l-libpng-apng-1.6.43
  /nix/store/vchsjnn7pzn918vbsj95ipynph2i921b-libpsl-0.21.5

2025-12-05T09:23:34.099054948Z [inf]    /nix/store/gbbqq9dbzkrxf2sw34xnk6lqmsiw70sv-libseccomp-2.5.5-lib

2025-12-05T09:23:34.099071544Z [inf]    /nix/store/grvlmx3gv28yrq4dygr17ks24bd2m62n-libselinux-3.7
  /nix/store/2iw8sjy4fwxgdbaik1wwb9fccid87ifp-libssh2-1.11.0
  /nix/store/7fy5ikjlzx691lhrhwizwzlsqychdpwg-libtasn1-4.19.0
  /nix/store/b9mvbvsns7zk6kssxq2891cjqybvghis-libtiff-4.7.0
  /nix/store/7hpmrpicmvqgpnnj9i6470y1s7dh336z-libunistring-1.2
  /nix/store/adymqivyn5f261v88wwi3myn3kc4wx7h-libusb-1.0.27

2025-12-05T09:23:34.099077798Z [inf]    /nix/store/nhgd3jrrkcy9fssnhjc04w56phcw7md1-libwebp-1.4.0
  /nix/store/425hrsfq6nxy7mdwd09v9r439vf3qhkk-libxcb-1.17.0

2025-12-05T09:23:34.099090666Z [inf]    /nix/store/3nkb6rscay1w5ky9xziy7qnjl0i4dx25-libxcrypt-4.4.36
  /nix/store/h4xcr5vxpz2wj4igjwdw85vjcxicspbx-linux-headers-6.10
  /nix/store/8b0f1lj164bzy7y36wxg57qfrb8yz742-linux-pam-1.6.1

2025-12-05T09:23:34.099097688Z [inf]    /nix/store/fj4kfzzrb0jjc2z96kcklas807r92qhg-mailcap-2.1.54
  /nix/store/py23xbn1b57hzbzpsyyfkp1rv5mh5pwa-mpdecimal-4.0.0
  /nix/store/k9s1aafqr83v8v4qv28px2i457dx6ix9-mpfr-4.2.1

2025-12-05T09:23:34.099101346Z [inf]    /nix/store/c7qx9iq6lqfjd4dxrdd6723l6rvzsj5s-ncurses-6.4.20221231

2025-12-05T09:23:34.09910537Z [inf]    /nix/store/2damawsadpx1djd1bz21l44h7llzaxji-nettle-3.10
  /nix/store/lmzcgk8j47nrhdvibxw3x0y9qyh1y6fq-nghttp2-1.63.0-lib

2025-12-05T09:23:34.099108686Z [inf]    /nix/store/y23cagpycbm8g1bdb7chvin3ykibixc3-nspr-4.35

2025-12-05T09:23:34.099119853Z [inf]    /nix/store/m2916xwh1lw9m8v21r1p12ydqhx3hsn8-nss-3.101.2
  /nix/store/x159n2adp73c3gs7654wn2h5nnzmr0sa-openjpeg-2.5.2
  /nix/store/m8gwqmn8k3jm0gbcia358mz4y00lgmbc-openssl-3.3.2

2025-12-05T09:23:34.099147304Z [inf]    /nix/store/gqk69c3b19w439pvw9rhzq21jkhlsd9d-p11-kit-0.25.5
  /nix/store/3yv1shg4kg4ifkxzg2jgjsrrrd8s1w08-patch-2.7.6
  /nix/store/r9gxdanbg938b9vimis7akyawkyb0yax-patchelf-0.15.0
  /nix/store/svlfxp9ips8gphsjz7ah2lsnirm2fhql-pcre2-10.44
  /nix/store/pg37w2gymgf5rdlp00c3jn7hw37bnmyc-perl-5.40.0

2025-12-05T09:23:34.09915135Z [inf]    /nix/store/5si486bhpwp5zpvkbs1fwfzd3wzx2nf7-pixman-0.43.4
  /nix/store/ds5dgc14bxjsg0rma79y8x1dkphw2fk1-poppler-data-0.4.12

2025-12-05T09:23:34.099154846Z [inf]    /nix/store/z227kjngla4l7jn7a5719izxqrmm7vpw-poppler-utils-24.02.0

2025-12-05T09:23:34.099160943Z [inf]    /nix/store/akpkx8im2vj8992byg3wh6cmhhk4m34m-publicsuffix-list-0-unstable-2024-09-10
  /nix/store/xscbbcx260v1d9libcrc472jwx210bc0-python3-3.11.10

2025-12-05T09:23:34.099164869Z [inf]    /nix/store/rf0rvd79mdhy427nv1wv9shkc9nglijz-readline-8.2p13
  /nix/store/b4cqpglpjvkjhb8l4dh1ammpg8gk6h9p-sqlite-3.46.1

2025-12-05T09:23:34.099170344Z [inf]    /nix/store/1m9h3isxr4jh67yjjx540qf3sxwxhy3y-stdenv-linux
  /nix/store/fqd2pjar09wpad84nnngh2rwfzpz7k0x-systemd-minimal-256.7

2025-12-05T09:23:34.099173414Z [inf]    /nix/store/d6vkx8r7x989n00zk9i5yjdyhiypqgmv-systemd-minimal-libs-256.7

2025-12-05T09:23:34.099190545Z [inf]    /nix/store/5z7yfmp96ijpx0lhy5gpj65i38972330-tzdata-2024b
  /nix/store/blljh4gmw1c260jmmn6q9ycbwds90dxv-unbound-1.21.1-lib
  /nix/store/7hsml574k621n842nwnl8qhix3i2q6mv-update-autotools-gnu-config-scripts-hook
  /nix/store/2qdrzz3izjbs5z0hk2ahj40fcmiybk6j-util-linux-minimal-2.39.4-lib

2025-12-05T09:23:34.099196026Z [inf]    /nix/store/61m0ig5xdc23r78s9sj2g98wqrwcyvdn-util-linux-minimal-2.39.4-login
  /nix/store/wkqaqjbf8dyz056qkqynx49cf7jbs55c-util-linux-minimal-2.39.4-mount

2025-12-05T09:23:34.099206232Z [inf]    /nix/store/85jfmy6p9wl0rhsfmy6fr46jzplwmgx1-util-linux-minimal-2.39.4-swap
  /nix/store/1hf92di50fsyqxcgsfi3z48hc05rm1a9-xgcc-13.3.0-libgcc
  /nix/store/wp5xd6g6v3mafvdh2185v19diqqf0cm2-xz-5.6.3

2025-12-05T09:23:34.099211166Z [inf]    /nix/store/g0ih6cb93dm4n18bah982gsmayah3amy-xz-5.6.3-bin
  /nix/store/ncjma3lhr1sf6mqaczl9mfhjmp6ix58w-zlib-1.3.1

2025-12-05T09:23:34.099214106Z [inf]    /nix/store/5hg6h4zjxc3ax7j4ywn6ksd509yl4pmd-zstd-1.5.6
  /nix/store/ah32d19s3nfffv8hr7br48wj4q3r79d0-zstd-1.5.6-bin

2025-12-05T09:23:34.109399703Z [inf]  copying path '/nix/store/nzi7rdydpky7lxv6mlvgcdpvdasaxcmq-builder.pl' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.11131096Z [inf]  copying path '/nix/store/63kqkhyn0mwk5iam1vc96qmy1hhq5q7g-ghostscript-with-X-10.04.0-man' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.115944223Z [inf]  copying path '/nix/store/zls8qr49k7bkdfb9ncqz9w38q5m8zkld-gcc-13.3.0-man' from 'https://cache.nixos.org'...
copying path '/nix/store/6q2302j98mzvnbr9aizw3i6ana5aajqv-ghostscript-with-X-10.04.0-fonts' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.117864267Z [inf]  copying path '/nix/store/fj4kfzzrb0jjc2z96kcklas807r92qhg-mailcap-2.1.54' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.118348948Z [inf]  copying path '/nix/store/ds5dgc14bxjsg0rma79y8x1dkphw2fk1-poppler-data-0.4.12' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.118476304Z [inf]  copying path '/nix/store/5z7yfmp96ijpx0lhy5gpj65i38972330-tzdata-2024b' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.119298296Z [inf]  copying path '/nix/store/6rvfplkwwbipv2ky3zcab0w9fvib9cgc-dejavu-fonts-minimal-2.37' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.11946495Z [inf]  copying path '/nix/store/c91k93z9yr1cpia2pf5dr226imglrkg5-gcc-13.3.0-libgcc' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.119746224Z [inf]  copying path '/nix/store/vcwb5qr1yjn3pwbm9gnmvqmn1gwg9a1y-gnu-config-2024-01-01' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.120712264Z [inf]  copying path '/nix/store/h4xcr5vxpz2wj4igjwdw85vjcxicspbx-linux-headers-6.10' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.121214859Z [inf]  copying path '/nix/store/1hf92di50fsyqxcgsfi3z48hc05rm1a9-xgcc-13.3.0-libgcc' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.121390372Z [inf]  copying path '/nix/store/bcl5fxfdw4h562in7kgyz3m5xjx0wcc3-dns-root-data-2024-06-20' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.122068139Z [inf]  copying path '/nix/store/7hpmrpicmvqgpnnj9i6470y1s7dh336z-libunistring-1.2' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.122082998Z [inf]  copying path '/nix/store/akpkx8im2vj8992byg3wh6cmhhk4m34m-publicsuffix-list-0-unstable-2024-09-10' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.179615565Z [inf]  copying path '/nix/store/7hsml574k621n842nwnl8qhix3i2q6mv-update-autotools-gnu-config-scripts-hook' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.199757625Z [inf]  copying path '/nix/store/bhd4nlz0993jcsmp7b4fpgjyc9knh1yx-gcc-wrapper-13.3.0-man' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.209405601Z [inf]  copying path '/nix/store/8afqxzzfwf3kfr117ficqzla55az8fcm-fontconfig-2.15.0' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.239394766Z [inf]  copying path '/nix/store/3wjcy2waiy7cr1v0kvi73aj6i90d878d-libidn2-2.3.7' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.266981808Z [inf]  copying path '/nix/store/3bvxjkkmwlymr0fssczhgi39c3aj1l7i-glibc-2.40-36' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.899830515Z [inf]  copying path '/nix/store/j2v823114cc2dqfvprlcx9h7i941kknh-attr-2.5.2' from 'https://cache.nixos.org'...
copying path '/nix/store/mm0pa3z7kk6jh1i9rkxqxjqmd8h1qpxf-bash-5.2p37' from 'https://cache.nixos.org'...
copying path '/nix/store/q4hiqvr973mpf0g4jpqg8xa5r8p8qa18-brotli-1.1.0-lib' from 'https://cache.nixos.org'...
copying path '/nix/store/6amvjdayglsifq4lb2lrj4q5gwf4dicd-bzip2-1.0.8' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.89985746Z [inf]  copying path '/nix/store/b1rvxspjrw0f3y5iz4pcygams0n9yas4-ed-1.20.2' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.89992946Z [inf]  copying path '/nix/store/zx2bmicmgjh0inkgffd7agxz47j4xxql-expand-response-params' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.899991425Z [inf]  copying path '/nix/store/cnmw0v80xbp4ldc79an5kb2p8a3ia6k5-expat-2.6.3' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.900212616Z [inf]  copying path '/nix/store/1cd3p3kjh9c209s7832z8i3b8qcqggca-gawk-5.3.1' from 'https://cache.nixos.org'...
copying path '/nix/store/s94fwp43xhzkvw8l8nqslskib99yifzi-gcc-13.3.0-lib' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.900330752Z [inf]  copying path '/nix/store/h9bcdwky1hznar341kl52g7hidcjxfdc-gdbm-1.24-lib' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.900375029Z [inf]  copying path '/nix/store/zxglqixhhlfppn5z4sszil1cj27ip2jx-giflib-5.2.2' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.900408058Z [inf]  copying path '/nix/store/5571d6dklkwfcp1812dj4lxb0gl3w1yw-glibc-2.40-36-bin' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.900710134Z [inf]  copying path '/nix/store/az5vszpdy3i53lksl8rbjai7bc88r5zs-glibc-2.40-36-getent' from 'https://cache.nixos.org'...
copying path '/nix/store/iyrpqn6ana7j804dzis338n74kzznmj0-gnumake-4.4.1' from 'https://cache.nixos.org'...
copying path '/nix/store/13wxcn0j2wk911ahfkbvdq241rkprsv8-gnused-4.9' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.900789156Z [inf]  copying path '/nix/store/fbir2hb0b8b9n9by2qkmr4sjscds5017-gmp-6.3.0' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.915217838Z [inf]  copying path '/nix/store/nxy5dn4640120b49836q3xh6nzvfwswf-ijs-10.04.0' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.915486653Z [inf]  copying path '/nix/store/7g0kqn1d1jh67hn1bazamxg0kz1gl8sm-jbig2dec-0.20' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.915503336Z [inf]  copying path '/nix/store/qzsiapz58wbfn8k3j7cbby6n1v0scd53-keyutils-1.6.3-lib' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.918995847Z [inf]  copying path '/nix/store/hql3c9ylksa8hzavl1xr675ry4fqj1hb-getent-glibc-2.40-36' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.925286901Z [inf]  copying path '/nix/store/0dglgnjm2s5qg4ar6m33lpclqig0kg2x-acl-2.3.2' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.927247198Z [inf]  copying path '/nix/store/0kxxaix9l5dbih90491mv96zajsac57q-bzip2-1.0.8-bin' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.929722801Z [inf]  copying path '/nix/store/8ai72nk8pvdsn4lbw67n0i1rp65ygpdg-lcms2-2.16' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.933274116Z [inf]  copying path '/nix/store/ww7q95lqp62aa4d4ss2g5mblzagqz4c4-libICE-1.1.1' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.941016353Z [inf]  copying path '/nix/store/7ch80860hzh4hk2xlni7aikdv4nx5jjl-libXau-1.0.11' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.941159645Z [inf]  copying path '/nix/store/6rpcqg6k1kdjnvbcnfx7nm4p185bp2dr-libXdmcp-1.1.5' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.94170036Z [inf]  copying path '/nix/store/ycavj0wxnz72h0n7csvplbgfcrq25x5f-libcap-2.70-lib' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.943193157Z [inf]  copying path '/nix/store/r5s8n5fr61562pgrl5in513v9ww336wf-libdaemon-0.14' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.943691248Z [inf]  copying path '/nix/store/m8wfhgwjzi8kw3kcbwr241kp1k1nn8jb-libdeflate-1.22' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.943988269Z [inf]  copying path '/nix/store/qq5ksis6nqh587vl72xj484l8fivaajw-libevent-2.1.12' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.948615219Z [inf]  copying path '/nix/store/cqyjb712c5q3axw9qjij05dnji2a7z48-gnutar-1.35' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.949697041Z [inf]  copying path '/nix/store/0qiyy7llb8ldillvlvjz1pyawhs5cvpk-libffi-3.4.6' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.953812293Z [inf]  copying path '/nix/store/d73s0l3nbc9bpl4c8cg9j12bak5n2d5f-libjpeg-turbo-3.0.3' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.954260578Z [inf]  copying path '/nix/store/1v4kdwh68m221n160qxy1dgw64mg5z30-isl-0.20' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.954421468Z [inf]  copying path '/nix/store/vchsjnn7pzn918vbsj95ipynph2i921b-libpsl-0.21.5' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.955108786Z [inf]  copying path '/nix/store/gbbqq9dbzkrxf2sw34xnk6lqmsiw70sv-libseccomp-2.5.5-lib' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.955263136Z [inf]  copying path '/nix/store/7fy5ikjlzx691lhrhwizwzlsqychdpwg-libtasn1-4.19.0' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.956475845Z [inf]  copying path '/nix/store/425hrsfq6nxy7mdwd09v9r439vf3qhkk-libxcb-1.17.0' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.957912374Z [inf]  copying path '/nix/store/3nkb6rscay1w5ky9xziy7qnjl0i4dx25-libxcrypt-4.4.36' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.963283464Z [inf]  copying path '/nix/store/py23xbn1b57hzbzpsyyfkp1rv5mh5pwa-mpdecimal-4.0.0' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.963897793Z [inf]  copying path '/nix/store/k9s1aafqr83v8v4qv28px2i457dx6ix9-mpfr-4.2.1' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.968444974Z [inf]  copying path '/nix/store/c7qx9iq6lqfjd4dxrdd6723l6rvzsj5s-ncurses-6.4.20221231' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.968631376Z [inf]  copying path '/nix/store/lmzcgk8j47nrhdvibxw3x0y9qyh1y6fq-nghttp2-1.63.0-lib' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.969923456Z [inf]  copying path '/nix/store/y23cagpycbm8g1bdb7chvin3ykibixc3-nspr-4.35' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.973399744Z [inf]  copying path '/nix/store/m8gwqmn8k3jm0gbcia358mz4y00lgmbc-openssl-3.3.2' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.973712898Z [inf]  copying path '/nix/store/gqk69c3b19w439pvw9rhzq21jkhlsd9d-p11-kit-0.25.5' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.97650379Z [inf]  copying path '/nix/store/515aba55q2b288xzamgb2xl1y1x4sk13-audit-4.0' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.980123984Z [inf]  copying path '/nix/store/qfc6wq1wpxvkkjqa6xr5685ip97qc3sr-gzip-1.13' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.983985829Z [inf]  copying path '/nix/store/7vw61y339hgb9s457ga3il7crhh3zh53-libpaper-1.1.29' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.985316782Z [inf]  copying path '/nix/store/3yv1shg4kg4ifkxzg2jgjsrrrd8s1w08-patch-2.7.6' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.987689737Z [inf]  copying path '/nix/store/932dj5qwfzck90mnvqpd1f9hjqznaqdj-glibc-2.40-36-dev' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.994283997Z [inf]  copying path '/nix/store/svlfxp9ips8gphsjz7ah2lsnirm2fhql-pcre2-10.44' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.997315943Z [inf]  copying path '/nix/store/5si486bhpwp5zpvkbs1fwfzd3wzx2nf7-pixman-0.43.4' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.997335768Z [inf]  copying path '/nix/store/d6vkx8r7x989n00zk9i5yjdyhiypqgmv-systemd-minimal-libs-256.7' from 'https://cache.nixos.org'...

2025-12-05T09:23:34.999875874Z [inf]  copying path '/nix/store/2qdrzz3izjbs5z0hk2ahj40fcmiybk6j-util-linux-minimal-2.39.4-lib' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.001463669Z [inf]  copying path '/nix/store/wjvrhcaf0qjh4j463sz0fdday7qx8ga8-libmpc-1.3.1' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.003834545Z [inf]  copying path '/nix/store/61m0ig5xdc23r78s9sj2g98wqrwcyvdn-util-linux-minimal-2.39.4-login' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.007480032Z [inf]  copying path '/nix/store/wp5xd6g6v3mafvdh2185v19diqqf0cm2-xz-5.6.3' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.011380893Z [inf]  copying path '/nix/store/ncjma3lhr1sf6mqaczl9mfhjmp6ix58w-zlib-1.3.1' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.017453771Z [inf]  copying path '/nix/store/8nbr24sqvsvsfrb5d2nci1ylppjnrwr2-libX11-1.8.10' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.027324523Z [inf]  copying path '/nix/store/ywxfq90ijq9kys4g5wzyrg2f4in0iphd-binutils-2.43.1-lib' from 'https://cache.nixos.org'...
copying path '/nix/store/vkv9a83hknlnr7p2z8mwl16j5pb502gp-file-5.45' from 'https://cache.nixos.org'...
copying path '/nix/store/q8h3pgwxqcgr5v5m7a53hy64vn4n9s79-kexec-tools-2.0.29' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.029302241Z [inf]  copying path '/nix/store/d497qsaaabx4nqchkrrzvaimad6mp22l-libpng-apng-1.6.43' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.035739697Z [inf]  copying path '/nix/store/b4cqpglpjvkjhb8l4dh1ammpg8gk6h9p-sqlite-3.46.1' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.045679946Z [inf]  copying path '/nix/store/nysgss3ggh3dv7mz08n28h29lazxhyc1-gnugrep-3.11' from 'https://cache.nixos.org'...
copying path '/nix/store/grvlmx3gv28yrq4dygr17ks24bd2m62n-libselinux-3.7' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.049360509Z [inf]  copying path '/nix/store/g0ih6cb93dm4n18bah982gsmayah3amy-xz-5.6.3-bin' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.051427358Z [inf]  copying path '/nix/store/pg8kdhlacrhv0nsfpx91x9f56gaxqqvv-freetype-2.13.3' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.051678443Z [inf]  copying path '/nix/store/nhgd3jrrkcy9fssnhjc04w56phcw7md1-libwebp-1.4.0' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.052342264Z [inf]  copying path '/nix/store/r97qr0giscd7576l0177inhrvj9xw00v-libSM-1.2.4' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.052699504Z [inf]  copying path '/nix/store/wkqaqjbf8dyz056qkqynx49cf7jbs55c-util-linux-minimal-2.39.4-mount' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.063887281Z [inf]  copying path '/nix/store/adymqivyn5f261v88wwi3myn3kc4wx7h-libusb-1.0.27' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.066068774Z [inf]  copying path '/nix/store/85jfmy6p9wl0rhsfmy6fr46jzplwmgx1-util-linux-minimal-2.39.4-swap' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.093599324Z [inf]  copying path '/nix/store/ipqijizc7rqsxifxc6ky16hr5l0hpls2-glib-2.82.1' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.108185318Z [inf]  copying path '/nix/store/lbx3j21p2dsr1rc5j2s8zaprkkwlrq5x-db-4.8.30' from 'https://cache.nixos.org'...
copying path '/nix/store/avd3viplh1hsz0xcvi86wcfqxycrv2wd-gmp-with-cxx-6.3.0' from 'https://cache.nixos.org'...
copying path '/nix/store/i2bs001zwvii9qbhk6mm291gqybpij87-gmp-with-cxx-6.3.0' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.108210472Z [inf]  copying path '/nix/store/qyax1vn63hxggnj0fzbr2xyri3rikpgh-lerc-4.0.0' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.108284986Z [inf]  copying path '/nix/store/r9gxdanbg938b9vimis7akyawkyb0yax-patchelf-0.15.0' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.108340668Z [inf]  copying path '/nix/store/5hg6h4zjxc3ax7j4ywn6ksd509yl4pmd-zstd-1.5.6' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.110976901Z [inf]  copying path '/nix/store/znz0rdiqy03vx45mhayrxfhq2winhd9m-fontconfig-2.15.0-lib' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.112295889Z [inf]  copying path '/nix/store/m2916xwh1lw9m8v21r1p12ydqhx3hsn8-nss-3.101.2' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.114103462Z [inf]  copying path '/nix/store/pbixrqd120nnw8a0ygfpm3mnwlr1mbj7-binutils-2.43.1' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.122624069Z [inf]  copying path '/nix/store/v7dbfh5n7az2lcap0z1cv4jq0bikya8p-gcc-13.3.0' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.133933146Z [inf]  copying path '/nix/store/d7fhpn9bhzcn521clna2wffmq3ww21zs-libXext-1.3.6' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.133963765Z [inf]  copying path '/nix/store/rindram6f9gwanvazd2x543gis4yzqks-libXrender-0.9.11' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.135222075Z [inf]  copying path '/nix/store/f5rndjaqlq8v9fs70x8cz7r66z6nj4hs-libXt-1.3.0' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.144708257Z [inf]  copying path '/nix/store/2damawsadpx1djd1bz21l44h7llzaxji-nettle-3.10' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.146788971Z [inf]  copying path '/nix/store/sf6y4arqcm100rnnl3dhpg732i774zp6-coreutils-9.5' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.149637103Z [inf]  copying path '/nix/store/grmqrfmxxkbxk83vkki5s45dch8z58yf-kmod-31' from 'https://cache.nixos.org'...
copying path '/nix/store/pkh3j1nsqlq0gqiqbsdw7s1pjg5i9nb4-kmod-31-lib' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.149655296Z [inf]  copying path '/nix/store/b9mvbvsns7zk6kssxq2891cjqybvghis-libtiff-4.7.0' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.149746306Z [inf]  copying path '/nix/store/ah32d19s3nfffv8hr7br48wj4q3r79d0-zstd-1.5.6-bin' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.152079516Z [inf]  copying path '/nix/store/nns4azjdb9ly7c4mjd5bhnj9zbr03fr0-krb5-1.21.3-lib' from 'https://cache.nixos.org'...
copying path '/nix/store/2iw8sjy4fwxgdbaik1wwb9fccid87ifp-libssh2-1.11.0' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.191112695Z [inf]  copying path '/nix/store/blljh4gmw1c260jmmn6q9ycbwds90dxv-unbound-1.21.1-lib' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.195179548Z [inf]  copying path '/nix/store/x159n2adp73c3gs7654wn2h5nnzmr0sa-openjpeg-2.5.2' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.199798866Z [inf]  copying path '/nix/store/8b0f1lj164bzy7y36wxg57qfrb8yz742-linux-pam-1.6.1' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.234896374Z [inf]  copying path '/nix/store/alq4bqllykgwrif112yqgrn9g001kn7b-diffutils-3.10' from 'https://cache.nixos.org'...
copying path '/nix/store/psjqqbj19n3fqssn38hgz4cv7b7a9alp-findutils-4.10.0' from 'https://cache.nixos.org'...
copying path '/nix/store/n3c0dpm00k7s7wgq35b6w025g2ixg20r-kbd-2.6.4' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.234923524Z [inf]  copying path '/nix/store/pg37w2gymgf5rdlp00c3jn7hw37bnmyc-perl-5.40.0' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.264480699Z [inf]  copying path '/nix/store/vic96jkyhfvq58bwch08618zg72gdgkz-curl-8.10.1' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.266156743Z [inf]  copying path '/nix/store/d4n6v15i5sl6yxr4qkcw0dq3nmb85kb8-gnutls-3.8.6' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.314505431Z [inf]  copying path '/nix/store/1m9h3isxr4jh67yjjx540qf3sxwxhy3y-stdenv-linux' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.459306287Z [inf]  building '/nix/store/w9wjpgsiwxjv9p6166ax2mns747lmv2c-libraries.drv'...

2025-12-05T09:23:35.462797117Z [inf]  copying path '/nix/store/rf0rvd79mdhy427nv1wv9shkc9nglijz-readline-8.2p13' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.474892482Z [inf]  copying path '/nix/store/ydh8c59mzliwy6pvjbrmzvgirryn96qh-cairo-1.18.2' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.489522251Z [inf]  copying path '/nix/store/j5n790vpyjnqc9kz31s9k8limg5jbk37-bash-interactive-5.2p37' from 'https://cache.nixos.org'...
copying path '/nix/store/xscbbcx260v1d9libcrc472jwx210bc0-python3-3.11.10' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.531676911Z [inf]  copying path '/nix/store/z227kjngla4l7jn7a5719izxqrmm7vpw-poppler-utils-24.02.0' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.787003845Z [inf]  building '/nix/store/g3lchy17nx4gv4bw71jnpiinxs47bg4s-bc8f8d1be58e8c8383e683a06e1e1e57893fff87-env.drv'...

2025-12-05T09:23:35.791281228Z [inf]  copying path '/nix/store/fqd2pjar09wpad84nnngh2rwfzpz7k0x-systemd-minimal-256.7' from 'https://cache.nixos.org'...

2025-12-05T09:23:35.854102794Z [inf]  copying path '/nix/store/l13l2ipc1xn5npjrw511y0yfh4ghinmf-binutils-wrapper-2.43.1' from 'https://cache.nixos.org'...

2025-12-05T09:23:36.193069656Z [inf]  copying path '/nix/store/mpwzncl2rnvybrlcn1m6f3ixs08kj2rm-dbus-1.14.10-lib' from 'https://cache.nixos.org'...

2025-12-05T09:23:36.217108985Z [inf]  copying path '/nix/store/gc4s51ksbm026n2wcb68i1myk333zwdr-avahi-0.8' from 'https://cache.nixos.org'...

2025-12-05T09:23:36.273053831Z [inf]  copying path '/nix/store/ivbsicn5yzqqhvr64x9d88l8dz4m6n76-cups-2.4.11-lib' from 'https://cache.nixos.org'...

2025-12-05T09:23:36.34039588Z [inf]  copying path '/nix/store/3mfk8bbdm218328q4m8ldfdkir4s6969-cups-2.4.11' from 'https://cache.nixos.org'...

2025-12-05T09:23:36.617551749Z [inf]  copying path '/nix/store/00k65b5bmwji0q799jq6nc4drhww1ij2-ghostscript-with-X-10.04.0' from 'https://cache.nixos.org'...

2025-12-05T09:23:39.353953565Z [inf]  copying path '/nix/store/hgw57m0jh2w10jsv8x86ng267pm5sla8-gcc-wrapper-13.3.0' from 'https://cache.nixos.org'...

2025-12-05T09:23:39.417264791Z [inf]  building '/nix/store/h4ssnapghpmf0zaipfasy6z1bsc2j73x-bc8f8d1be58e8c8383e683a06e1e1e57893fff87-env.drv'...

2025-12-05T09:23:39.531364154Z [inf]  created 147 symlinks in user environment

2025-12-05T09:23:39.71808433Z [inf]  building '/nix/store/sfd0mirdxk000mhp329bhd7avwlmi109-user-environment.drv'...

2025-12-05T09:23:39.957272083Z [inf]  removing old generations of profile /nix/var/nix/profiles/per-user/root/profile

2025-12-05T09:23:39.9572916Z [inf]  removing profile version 1

2025-12-05T09:23:39.957425739Z [inf]  removing old generations of profile /nix/var/nix/profiles/per-user/root/channels

2025-12-05T09:23:39.957629707Z [inf]  removing old generations of profile /nix/var/nix/profiles/per-user/root/profile

2025-12-05T09:23:39.957709348Z [inf]  removing old generations of profile /nix/var/nix/profiles/per-user/root/channels

2025-12-05T09:23:39.960836025Z [inf]  finding garbage collector roots...

2025-12-05T09:23:39.961118696Z [inf]  removing stale link from '/nix/var/nix/gcroots/auto/lzjbmb2ry0z7lma2fvpqprb12921pnb5' to '/nix/var/nix/profiles/per-user/root/profile-1-link'

2025-12-05T09:23:39.96603097Z [inf]  deleting garbage...

2025-12-05T09:23:39.972570955Z [inf]  deleting '/nix/store/a9qf4wwhympzs35ncp80r185j6a21w07-user-environment'

2025-12-05T09:23:40.022128906Z [inf]  deleting '/nix/store/253kwn1730vnay87xkjgxa2v97w3y079-user-environment.drv'

2025-12-05T09:23:40.02323314Z [inf]  deleting '/nix/store/hn5mrh362n52x8wwab9s1v6bgn4n5c94-env-manifest.nix'

2025-12-05T09:23:40.023917425Z [inf]  deleting '/nix/store/1m9h3isxr4jh67yjjx540qf3sxwxhy3y-stdenv-linux'

2025-12-05T09:23:40.024227414Z [inf]  deleting '/nix/store/7hsml574k621n842nwnl8qhix3i2q6mv-update-autotools-gnu-config-scripts-hook'

2025-12-05T09:23:40.024474969Z [inf]  deleting '/nix/store/vcwb5qr1yjn3pwbm9gnmvqmn1gwg9a1y-gnu-config-2024-01-01'

2025-12-05T09:23:40.024860298Z [inf]  deleting '/nix/store/3yv1shg4kg4ifkxzg2jgjsrrrd8s1w08-patch-2.7.6'

2025-12-05T09:23:40.025480417Z [inf]  deleting '/nix/store/b1rvxspjrw0f3y5iz4pcygams0n9yas4-ed-1.20.2'

2025-12-05T09:23:40.026125523Z [inf]  deleting '/nix/store/psjqqbj19n3fqssn38hgz4cv7b7a9alp-findutils-4.10.0'

2025-12-05T09:23:40.029060588Z [inf]  deleting '/nix/store/pg37w2gymgf5rdlp00c3jn7hw37bnmyc-perl-5.40.0'

2025-12-05T09:23:40.054877149Z [inf]  deleting '/nix/store/iyrpqn6ana7j804dzis338n74kzznmj0-gnumake-4.4.1'

2025-12-05T09:23:40.057172174Z [inf]  deleting '/nix/store/13wxcn0j2wk911ahfkbvdq241rkprsv8-gnused-4.9'

2025-12-05T09:23:40.059863033Z [inf]  deleting '/nix/store/r9gxdanbg938b9vimis7akyawkyb0yax-patchelf-0.15.0'

2025-12-05T09:23:40.060448151Z [inf]  deleting '/nix/store/1cd3p3kjh9c209s7832z8i3b8qcqggca-gawk-5.3.1'

2025-12-05T09:23:40.063336216Z [inf]  deleting '/nix/store/vkv9a83hknlnr7p2z8mwl16j5pb502gp-file-5.45'

2025-12-05T09:23:40.063967713Z [inf]  deleting '/nix/store/nzi7rdydpky7lxv6mlvgcdpvdasaxcmq-builder.pl'

2025-12-05T09:23:40.064300139Z [inf]  deleting '/nix/store/yfvhrcz7h68gxk06hfgq78din42454ha-source'

2025-12-05T09:23:41.218820484Z [inf]  deleting '/nix/store/alq4bqllykgwrif112yqgrn9g001kn7b-diffutils-3.10'

2025-12-05T09:23:41.221530487Z [inf]  deleting '/nix/store/cqyjb712c5q3axw9qjij05dnji2a7z48-gnutar-1.35'

2025-12-05T09:23:41.22438448Z [inf]  deleting '/nix/store/y0fjd2rszhr48f61350q7ym16c1naizn-libraries'

2025-12-05T09:23:41.224877948Z [inf]  deleting unused links...

2025-12-05T09:23:42.703292577Z [inf]  note: currently hard linking saves 9.89 MiB

2025-12-05T09:23:42.791053294Z [inf]  20 store paths deleted, 244.56 MiB freed

2025-12-05T09:23:43.113075394Z [inf]  [stage-0 4/9] RUN nix-env -if .nixpacks/nixpkgs-bc8f8d1be58e8c8383e683a06e1e1e57893fff87.nix && nix-collect-garbage -d
2025-12-05T09:23:43.116775595Z [inf]  [stage-0 5/9] COPY . /app/.
2025-12-05T09:23:43.349342218Z [inf]  [stage-0 5/9] COPY . /app/.
2025-12-05T09:23:43.351413110Z [inf]  [stage-0 6/9] RUN --mount=type=cache,id=s/2f451e60-6351-4513-93ca-e1c0f23ab1f0-/root/cache/pip,target=/root/.cache/pip pip install --upgrade pip
2025-12-05T09:23:43.41184984Z [inf]  /bin/bash: line 1: pip: command not found

2025-12-05T09:23:43.429486086Z [err]  [stage-0 6/9] RUN --mount=type=cache,id=s/2f451e60-6351-4513-93ca-e1c0f23ab1f0-/root/cache/pip,target=/root/.cache/pip pip install --upgrade pip
2025-12-05T09:23:43.451006242Z [err]  Dockerfile:20
2025-12-05T09:23:43.451040844Z [err]  -------------------
2025-12-05T09:23:43.451049850Z [err]  18 |     ENV NIXPACKS_PATH=/opt/venv/bin:$NIXPACKS_PATH
2025-12-05T09:23:43.451054456Z [err]  19 |     COPY . /app/.
2025-12-05T09:23:43.451060854Z [err]  20 | >>> RUN --mount=type=cache,id=s/2f451e60-6351-4513-93ca-e1c0f23ab1f0-/root/cache/pip,target=/root/.cache/pip pip install --upgrade pip
2025-12-05T09:23:43.451065494Z [err]  21 |     RUN --mount=type=cache,id=s/2f451e60-6351-4513-93ca-e1c0f23ab1f0-/root/cache/pip,target=/root/.cache/pip pip install -r requirements.txt
2025-12-05T09:23:43.451069976Z [err]  22 |
2025-12-05T09:23:43.451075009Z [err]  -------------------
2025-12-05T09:23:43.451082562Z [err]  ERROR: failed to build: failed to solve: process "/bin/bash -ol pipefail -c pip install --upgrade pip" did not complete successfully: exit code: 127
2025-12-05T09:23:43.458981466Z [err]  Error: Docker build failed